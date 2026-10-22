"""One-shot diagnostic for the official BOATRACE payoff listing.

Only prints bounded structural samples and response status; does not store the HTML.
"""
import re
from urllib.request import Request, urlopen
from html.parser import HTMLParser

class Probe(HTMLParser):
    def __init__(self):
        super().__init__()
        self.tables=0; self.rows=0; self.heads=[]; self.cells=[]; self.images=[]; self.stack=[]
        self.current_cell=None; self.current_row=None
    def handle_starttag(self,tag,attrs):
        a=dict(attrs)
        if tag=="table": self.tables+=1
        if tag=="tr":
            self.rows+=1; self.current_row=[]
        if tag in ("th","td"):
            self.current_cell={"tag":tag,"attrs":a,"text":"","images":[]}
        if tag=="img":
            if self.current_cell is not None:
                self.current_cell["images"].append({"alt":a.get("alt"),"src":a.get("src"),"class":a.get("class")})
            if len(self.images)<15:self.images.append({"alt":a.get("alt"),"src":a.get("src"),"class":a.get("class")})
    def handle_data(self,value):
        if self.current_cell is not None:self.current_cell["text"]+=value
    def handle_endtag(self,tag):
        if tag in ("th","td") and self.current_cell is not None:
            if self.current_row is not None:self.current_row.append(self.current_cell)
            self.current_cell=None
        if tag=="tr" and self.current_row is not None:
            if len(self.heads)<15:
                self.heads.append(self.current_row)
            self.current_row=None

def download(u):
    request=Request(u,headers={"User-Agent":"Mozilla/5.0 (compatible; BOATLAB-research; read-only)"})
    with urlopen(request, timeout=20) as response:
        data=response.read(1_500_000)
        ct=response.headers.get("Content-Type")
        return response.status,response.url,ct,data

if __name__=="__main__":
    for url in ("https://www.boatrace.jp/robots.txt","https://www.boatrace.jp/owpc/pc/race/pay?hd=20261022"):
        try:
            status,final,ct,raw=download(url)
            print("URL",url,"STATUS",status,"FINAL",final,"CTYPE",ct,"LENGTH",len(raw))
            s=raw.decode("utf-8","replace")
            if "robots.txt" in url:
                print("ROBOTS_HEAD",repr(s[:2800]))
            else:
                x=Probe(); x.feed(s)
                print("HTML_COUNT",{"tables":x.tables,"rows":x.rows,"images":x.images})
                print("ROWS_SAMPLE",repr(x.heads[:8])[:14000])
                for q in ["本日の払戻金","10月22日レース","徳山","3連単","レース中止"]:
                    ix=s.find(q)
                    print("NEAR",q,ix,repr(s[max(0,ix-350):ix+650])[:1200])
                # Show classes around table names for reliable parser design.
                for fragment in re.findall(r'<table.{0,250}>',s,re.I)[:12]:
                    print("TABLE_TAG",repr(fragment))
        except Exception as ex:
            print("ERROR",url,type(ex).__name__,str(ex))
