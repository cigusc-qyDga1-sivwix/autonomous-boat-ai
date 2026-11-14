"""Approved direct media in bounded RAM. Reused existing source/FFmpeg helpers.

Origins: scripts/mikuni_video_autocollect.py (04c2e08),
scripts/mikuni_video_ephemeral.py (3f418e6). No player scraping or model imports.
"""
from __future__ import annotations
import hashlib
import io
import ipaddress
import math
import os
import re
import subprocess
from urllib.parse import urlparse
from urllib.request import Request, build_opener, HTTPSHandler, HTTPRedirectHandler

MAX_VIDEO_BYTES = 125829120
ACCEPTED_TYPES = ("video/mp4", "video/webm", "video/quicktime", "video/x-msvideo", "application/octet-stream")
FRAME_LIMIT = 48
FFMPEG_TIMEOUT_S = 35
JPEG_OUTPUT_LIMIT = 16 * 1024 * 1024

def _valid_host(host):
    if not isinstance(host,str) or not host or len(host)>253:
        return False
    host=host.lower()
    if host in ("localhost","localhost.localdomain") or host.endswith(".local"):
        return False
    try:
        # Never accept a literal IP, including non-routable addresses.
        ipaddress.ip_address(host)
        return False
    except ValueError:
        pass
    if not re.fullmatch(r"[a-z0-9-]+(?:\.[a-z0-9-]+)+",host):
        return False
    return all(label and len(label)<=63 and not label.startswith("-")
               and not label.endswith("-") for label in host.split("."))

def _check_url(url,allowed_hosts):
    parsed=urlparse(url)
    if (parsed.scheme!="https" or parsed.username is not None or
        parsed.password is not None or parsed.port not in (None,443) or
        parsed.fragment or not _valid_host(parsed.hostname) or
        parsed.hostname.lower() not in allowed_hosts):
        raise ValueError("unapproved_media_host_or_transport")
    if len(url)>4096 or not parsed.path.startswith("/"):
        raise ValueError("invalid_media_path")
    return parsed.hostname.lower()

class StrictRedirect(HTTPRedirectHandler):
    """Reject redirects to unexpected domains, plaintext or local targets."""
    def __init__(self,hosts):
        super().__init__()
        self.hosts=hosts
    def redirect_request(self,req,fp,code,msg,headers,newurl):
        _check_url(newurl,self.hosts)
        return super().redirect_request(req,fp,code,msg,headers,newurl)

def _media_magic(sample):
    return (len(sample)>=12 and sample[4:8]==b"ftyp" or
            sample.startswith(b"\x1a\x45\xdf\xa3") or
            sample.startswith(b"RIFF") and sample[8:12]==b"AVI ")

def receive_approved_video(url, allowed_hosts):
    """Read only media bytes into RAM; limit size and reject HTML/HLS/redirects."""
    _check_url(url,allowed_hosts)
    req=Request(url,headers={
        "Accept":"video/mp4,video/webm,video/quicktime,video/x-msvideo",
        "User-Agent":"BOAT-LAB-venue-authorized-ephemeral-video-research/0.1",
    })
    opener=build_opener(HTTPSHandler(),StrictRedirect(allowed_hosts))
    with opener.open(req,timeout=14) as response:
        _check_url(response.geturl(),allowed_hosts)
        content_type=response.headers.get("Content-Type","").split(";",1)[0].lower().strip()
        if content_type not in ACCEPTED_TYPES:
            raise ValueError("not_direct_video_media")
        length=response.headers.get("Content-Length")
        if length and length.isdigit() and int(length)>MAX_VIDEO_BYTES:
            raise ValueError("video_too_large")
        first=response.read(32)
        if not _media_magic(first):
            raise ValueError("not_recognized_direct_video_container")
        sink=io.BytesIO()
        sink.write(first)
        while True:
            chunk=response.read(1048576)
            if not chunk:break
            if sink.tell()+len(chunk)>MAX_VIDEO_BYTES:
                raise ValueError("video_too_large")
            sink.write(chunk)
    blob=sink.getvalue()
    return blob,{"sha256":hashlib.sha256(blob).hexdigest(),
                 "file_size":len(blob),"content_type":content_type}

def _split_jpegs(jpeg_stream):
    """Extract bounded JPEG images from FFmpeg stdout (not saved to disk)."""
    if len(jpeg_stream)>JPEG_OUTPUT_LIMIT:
        raise ValueError("video_frame_output_too_large")
    cursor=0
    images=[]
    while len(images)<FRAME_LIMIT:
        start=jpeg_stream.find(b"\xff\xd8",cursor)
        if start<0:break
        end=jpeg_stream.find(b"\xff\xd9",start+2)
        if end<0:break
        images.append(jpeg_stream[start:end+2])
        cursor=end+2
    if not images:raise ValueError("video_no_decodable_frames")
    return images

def decode_in_memory(blob, *, runner=subprocess.run, start_seconds=0, sample_interval_s=.5):
    """FFmpeg reads from stdin; scaled JPEG frames from stdout, never a file.

    FFmpeg executable must be installed on the runner. Results are capped.
    The input bytes are transient and are discarded after processing.
    """
    if not isinstance(blob,bytes) or not blob or len(blob)>MAX_VIDEO_BYTES or not _media_magic(blob[:32]):
        raise ValueError("not_recognized_direct_video_container")
    if (isinstance(start_seconds,bool) or not isinstance(start_seconds,(int,float))
        or not math.isfinite(start_seconds) or not 0<=start_seconds<=300):
        raise ValueError("clip_start_seconds_invalid")
    if (isinstance(sample_interval_s,bool) or not isinstance(sample_interval_s,(int,float))
        or not math.isfinite(sample_interval_s) or not .1<=sample_interval_s<=10):
        raise ValueError("decode_sample_interval_invalid")
    args=["ffmpeg","-hide_banner","-loglevel","error",
          "-nostdin","-i","pipe:0",
          "-an","-sn","-dn",
          "-ss",f"{start_seconds:.3f}",
          "-vf",f"fps={1/sample_interval_s:.6g},scale='min(640,iw)':-2",
          "-frames:v",str(FRAME_LIMIT),
          "-f","image2pipe","-vcodec","mjpeg","pipe:1"]
    try:
        result=runner(args,input=blob,stdout=subprocess.PIPE,stderr=subprocess.PIPE,
                      timeout=FFMPEG_TIMEOUT_S,check=False)
    except FileNotFoundError as exc:
        raise RuntimeError("ffmpeg_not_available") from exc
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError("ffmpeg_timed_out") from exc
    if result.returncode!=0:
        # Some MP4 moov indices need seeking, which regular stdin cannot do.
        # Linux anonymous memfd is seekable RAM (not a persistent video file).
        # Never write video to /tmp or the repository.
        if not hasattr(os,"memfd_create"):
            raise ValueError("video_decode_failed")
        fd=os.memfd_create("boatlabs-ephemeral-video",flags=0)
        try:
            offset=0
            while offset<len(blob):
                written=os.write(fd,blob[offset:offset+1048576])
                if written<=0:raise ValueError("in_memory_video_write_failed")
                offset+=written
            os.lseek(fd,0,os.SEEK_SET)
            fd_args=[a if a!="pipe:0" else f"/proc/self/fd/{fd}" for a in args]
            try:
                result=runner(fd_args,stdout=subprocess.PIPE,stderr=subprocess.PIPE,
                              timeout=FFMPEG_TIMEOUT_S,check=False,pass_fds=(fd,))
            except subprocess.TimeoutExpired as exc:
                raise RuntimeError("ffmpeg_timed_out") from exc
            if result.returncode!=0:
                raise ValueError("video_decode_failed")
        finally:
            os.close(fd)
    return _split_jpegs(result.stdout)
