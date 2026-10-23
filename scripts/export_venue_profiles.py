"""Export a read-only all-24-venue manifest consumed by BOAT LAB PWA."""
import json
from pathlib import Path
try:
    from scripts.venue_profiles import VENUE_PROFILES
except ModuleNotFoundError:
    # Running as "python scripts/export_venue_profiles.py" sets sys.path to scripts/.
    from venue_profiles import VENUE_PROFILES

def main():
    target=Path("app/data/venue-profiles.json")
    target.parent.mkdir(parents=True,exist_ok=True)
    document={
      "schema":"boatlabs.venue_profiles.v1",
      "version":"experimental-0.1-20261023",
      "reference_type":"third-party aggregate; not calibrated winner probabilities",
      "description":"各場の水面・風・戦法を検証する試験設定。個別レースの実測風向・潮位を仮定しない。",
      "profiles":[VENUE_PROFILES[f"{i:02d}"] for i in range(1,25)]
    }
    target.write_text(json.dumps(document,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(f"Wrote {len(document['profiles'])} profiles into {target}")

if __name__=="__main__":
    main()
