"""Outside archive research tests: mapping, accuracy of descriptive rates, leak guard."""
import tempfile
import json
from pathlib import Path
from research_outside_roles import rows_from_docs, summarize, research

def make_record(code,finish,decision="まくり",courses=(1,2,3,4,5,6)):
    return {"race_code":code,"venue":"唐津",
            "boats":[{"lane":i+1,"course":courses[i]} for i in range(6)],
            "result":{"source":"BoatraceCSV/realtime_unofficial",
                      "finish":finish,"decision":decision}}
def main():
    def doc(*records):
        return {"schema":"boatlabs.exhibition_research.v1","event_date":"2026-10-24",
                "records":list(records)}
    a=make_record("202610242301","4-5-1")
    b=make_record("202610242302","1-5-6","逃げ")
    c=make_record("202610242303","6-3-4","まくり差し",
                 (1,3,2,4,6,5))
    invalid=make_record("202610242304","5-5-2")
    late=make_record("202610242305","6-5-1")
    late["result"]["source"]="manual_not_verified"
    rows=rows_from_docs([doc(a,b,c,invalid,late),doc(a)])
    assert len(rows)==3,rows
    assert rows[0]["finish_courses"]==(4,5,1)
    assert rows[2]["finish_courses"]==(5,2,4)
    summary=summarize(rows)
    assert summary["sample_races"]==3
    assert summary["course_finish"]["4"]["first"]==1
    assert summary["course_finish"]["5"]["first"]==1
    assert summary["course_finish"]["5"]["second"]==2
    assert summary["course_finish"]["6"]["third"]==1
    assert summary["outside_attack_follow"]["4"]["fifth_second"]==1
    assert summary["assessment"]=="insufficient_for_parameter_learning"
    assert "not a predictive" in summary["caveat"]
    assert not any(k in summary for k in ("winning_tickets","prediction","payouts"))
    with tempfile.TemporaryDirectory() as tmp:
        path=Path(tmp)
        (path/"2026-10-24.json").write_text(json.dumps(doc(a,b,c),ensure_ascii=False),encoding="utf-8")
        (path/"2026-10-23.json").write_text(json.dumps(doc(late),ensure_ascii=False),encoding="utf-8")
        (path/"outside-role-research-latest.json").write_text("{}",encoding="utf-8")
        result=research(path)
        assert result["sample_races"]==3
    print("Outside-course historical attack/follow descriptive research: PASS")

if __name__=="__main__":
    main()
