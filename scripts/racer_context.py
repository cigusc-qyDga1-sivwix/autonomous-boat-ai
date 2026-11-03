"""Fresh, allowlisted racer/card context for future four-factor forecasts only."""
from concurrent.futures import ThreadPoolExecutor
import re
import math
from statistics import fmean, pstdev
from datetime import datetime, timedelta, timezone
if __package__:
    from .ingest_global_intelligence import fetch_csv, numeric, source_url
else:
    from ingest_global_intelligence import fetch_csv, numeric, source_url
JST = timezone(timedelta(hours=9))


def in_meeting_start_consistency(card, lane):
    """Read only prior *observed* in-meeting starts in current pre-cutoff card.

    Never use the current race's outcome, final ST, or any postrace CSV.
    Missing values and F/L are not silently treated as fast legal starts.
    This descriptive feature is not a calibrated predicted start.
    """
    if not isinstance(card, dict) or lane not in range(1, 7):
        return {
            "meeting_st_legal_count": 0, "meeting_st_mean": None,
            "meeting_st_sd": None, "meeting_st_recent_mean": None,
            "meeting_st_recent_minus_older": None,
            "meeting_st_f_count": 0,
        }
    values = []
    flying = 0
    for day_index in range(1, 8):
        for session in (1, 2):
            key = f"艇{lane}_節D{day_index}走{session}_"
            race = numeric(card.get(key + "R番号"))
            if race is None or not race.is_integer() or not 1 <= race <= 12:
                continue
            start = numeric(card.get(key + "ST"))
            if start is None:
                continue
            if -.5 <= start < 0:
                flying += 1
            elif 0 <= start <= .40:
                values.append(start)
    count = len(values)
    result = {
        "meeting_st_legal_count": count,
        "meeting_st_mean": round(fmean(values), 4) if count >= 3 else None,
        "meeting_st_sd": round(pstdev(values), 4) if count >= 3 else None,
        "meeting_st_recent_mean": round(fmean(values[-3:]), 4) if count >= 3 else None,
        "meeting_st_recent_minus_older": (
            round(fmean(values[-3:]) - fmean(values[:-3]), 4)
            if count >= 6 else None
        ),
        "meeting_st_f_count": flying,
    }
    return result


def collect(day):
    with ThreadPoolExecutor(max_workers=2) as pool:
        tasks={key:pool.submit(fetch_csv,key,day) for key in ('race_cards','waku10')}
        fetched={key:job.result() for key,job in tasks.items()}
    by_source={key:{r.get('レースコード'):r for r in rows} for key,(rows,_) in fetched.items()}
    result={}
    for code,card in by_source['race_cards'].items():
        if not isinstance(code,str) or len(code)!=12 or code[:8]!=day.strftime('%Y%m%d'):continue
        waku=by_source['waku10'].get(code,{})
        boats={}
        for lane in range(1,7):
            p=f'艇{lane}_';rid=numeric(card.get(p+'登録番号'))
            if rid is None or not rid.is_integer():continue
            values={k:numeric(card.get(p+field)) for k,field in (
                ('national_top3','全国3連対率'),('local_win','当地勝率'),
                ('local_top3','当地3連対率'),('motor_top3','モーター3連対率'))}
            values.update({k:numeric(waku.get(p+field)) for k,field in (
                ('frame_win','枠番別勝率'),('frame_st','枠番別平均ST'),
                ('frame_start_order','枠番別平均スタート順'))})
            # New fields are advisory-only. The formal prediction model reads
            # an explicit allowlist and does NOT reweight these automatically.
            values.update(in_meeting_start_consistency(card, lane))
            boats[lane]={'racer_id':int(rid),'lane':lane,'values':values,
                         'sources':{key:meta for key,(_,meta) in fetched.items()}}
        result[code]=boats
    return result


def validated(row, racer, lane, now, day):
    """Never join by name alone, silently cross days, or use late/future captures."""
    if not row or row.get('lane')!=lane:return None
    rid=numeric(racer.get('number'))
    if rid is None or rid!=row.get('racer_id'):return None
    sources=row.get('sources') or {}
    card=sources.get('race_cards') or {}
    if card.get('state')!='available' or card.get('url')!=source_url('race_cards',day) or not re.fullmatch(r'[a-f0-9]{64}',card.get('sha256') or ''):return None
    try:
        captured=datetime.fromisoformat(card['fetched_at_utc'])
        if captured.tzinfo is None or not 0<=(now-captured).total_seconds()<=1800:return None
        if captured.astimezone(JST).date()!=day:return None
    except (KeyError,ValueError,TypeError):return None
    clean={'racer_id':int(rid),'lane':lane,'values':dict(row.get('values') or {}),'sources':{'race_cards':card}}
    waku=sources.get('waku10') or {}
    try:
        stamp=datetime.fromisoformat(waku['fetched_at_utc'])
        good=waku.get('state')=='available' and waku.get('url')==source_url('waku10',day) and bool(re.fullmatch(r'[a-f0-9]{64}',waku.get('sha256') or '')) and stamp.tzinfo is not None and 0<=(now-stamp).total_seconds()<=1800 and stamp.astimezone(JST).date()==day
    except (KeyError,ValueError,TypeError):good=False
    if good:clean['sources']['waku10']=waku
    else:
        for key in ('frame_win','frame_st','frame_start_order'):clean['values'][key]=None
    return clean
