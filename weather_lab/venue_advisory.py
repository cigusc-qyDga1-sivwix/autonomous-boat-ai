"""Research-only, non-betting venue weather alerts.

Official water-surface descriptions are qualitative context; thresholds below
are uncalibrated *monitoring* triggers, not win-rate coefficients.
Never infer wind orientation from the source's raw numeric wind code.
Never infer tide stage/current from a nearby tide table without site mapping.
"""
from __future__ import annotations

from .venue_special_conditions import evaluate as evaluate_special_conditions

VENUES = {
    "01": {"name": "桐生", "focus": "冬春の赤城おろし／強風と水面荒れ", "water": "wind", "official_url": "https://www.kiryu-kyotei.com/modules/datafile/?page=index_suimen", "forecast_scope": True},
    "02": {"name": "戸田", "focus": "狭い1マーク・風によるスタート／旋回の乱れ", "water": "wind", "official_url": "https://www.boatrace-toda.jp/data/suimen_guide.html", "forecast_scope": True},
    "03": {"name": "江戸川", "focus": "河川の流れ・潮・風（取得監視のみ、正式予想対象外）", "water": "tidal", "official_url": "https://www.boatrace.jp/owpc/pc/site/place/stadium/br03/", "forecast_scope": False},
    "04": {"name": "平和島", "focus": "潮位差・冬の向かい風・2マークの道中逆転", "water": "tidal", "official_url": "https://www.heiwajima.gr.jp/01suimen/01suimen.htm", "forecast_scope": True},
    "05": {"name": "多摩川", "focus": "比較的静穏でも突風・風向変化は当日観測で確認", "water": "wind", "official_url": "https://www.boatrace.jp/owpc/pc/site/place/stadium/br05/", "forecast_scope": True},
    "06": {"name": "浜名湖", "focus": "広い水面・冬の追い風／夏の向かい風・水位変化", "water": "tidal", "official_url": "https://www.boatrace-hamanako.jp/sp/index.php?page=datafile-suimen", "forecast_scope": True},
    "07": {"name": "蒲郡", "focus": "普段は静穏、例外的な風・波と2マーク逆転", "water": "wind", "official_url": "https://www.gamagori-kyotei.com/sp/01data/01data.htm", "forecast_scope": True},
    "08": {"name": "常滑", "focus": "水位は自動制御。外海の潮位を補正に直結させない", "water": "controlled", "official_url": "https://www.boatrace-tokoname.jp/modules/datafile/?page=index_suimen", "forecast_scope": True},
    "09": {"name": "津", "focus": "強風で急に荒れる。公式が風速約5mを注意目安と説明", "water": "wind", "official_url": "https://www.boatrace-tsu.com/modules/datafile/?page=index_suimen", "forecast_scope": True},
    "10": {"name": "三国", "focus": "冬の北風と追い風、1マーク流れからの差し・2マーク引き波", "water": "wind", "official_url": "https://www.boatrace-mikuni.jp/sp/index.php?page=datafile-suimen", "forecast_scope": True},
    "11": {"name": "びわこ", "focus": "春夏の沖からの風・湖面の波・標高", "water": "wind", "official_url": "https://www.boatrace.jp/owpc/pc/site/place/stadium/br11/", "forecast_scope": True},
    "12": {"name": "住之江", "focus": "護岸からの反射波と冬の2マーク付近のビル風", "water": "wind", "official_url": "https://www.suminoe.gr.jp/asp/suminoe/sp/suimen/suimen.asp", "forecast_scope": True},
    "13": {"name": "尼崎", "focus": "通常は静水面。公式は6m以上の風と波立ちを注意", "water": "wind", "official_url": "https://www.boatrace-amagasaki.jp/sp/index.php?page=datafile-suimen", "forecast_scope": True},
    "14": {"name": "鳴門", "focus": "水面の狭まり・干満差と攻め艇のターン", "water": "tidal", "official_url": "https://n14.jp/modules/datafile/?page=index_suimen", "forecast_scope": True},
    "15": {"name": "丸亀", "focus": "冬の向かい風・潮の出入り・満潮時2マークの荒れ", "water": "tidal", "official_url": "https://www.marugameboat.jp/01suimen/01suimen.htm", "forecast_scope": True},
    "16": {"name": "児島", "focus": "満潮時のうねり、満潮と追い風の複合条件", "water": "tidal", "official_url": "https://www.kojimaboat.jp/01suimen/01suimen.htm", "forecast_scope": True},
    "17": {"name": "宮島", "focus": "大きな干満差・満潮時のうねり・潮向", "water": "tidal", "official_url": "https://www.boatrace-miyajima.com/surface.html", "forecast_scope": True},
    "18": {"name": "徳山", "focus": "上げ潮と風の重なり・2マーク引き波", "water": "tidal", "official_url": "https://www.boatrace-tokuyama.jp/sp/index.php?page=datafile-suimen", "forecast_scope": True},
    "19": {"name": "下関", "focus": "2017年の堤防改修後は外海の波が入りにくい。潮位からの一律補正禁止", "water": "controlled", "official_url": "https://www.boatrace-shimonoseki.jp/sp/index.php?page=datafile-suimen", "forecast_scope": True},
    "20": {"name": "若松", "focus": "2マーク側からの潮の出入り・満潮時1マーク潮だまり", "water": "tidal", "official_url": "https://www.wmb.jp/modules/datafile/?page=index_suimen", "forecast_scope": True},
    "21": {"name": "芦屋", "focus": "1マーク裏の葦による消波。強風時は現地波高を確認", "water": "wind", "official_url": "https://www.boatrace.jp/owpc/pc/site/place/stadium/br21/", "forecast_scope": True},
    "22": {"name": "福岡", "focus": "河口近くの1マーク、満潮時の難水面とセンター攻め", "water": "tidal", "official_url": "https://www.boatrace.jp/owpc/pc/site/place/stadium/br22/", "forecast_scope": True},
    "23": {"name": "唐津", "focus": "朝夕の向かい風・追い風切替、ピット位置変更後の進入", "water": "wind", "official_url": "https://www.boatrace-karatsu.jp/modules/datafile/?page=index_suimen", "forecast_scope": True},
    "24": {"name": "大村", "focus": "時間帯による風向変化、満潮時2マークを監視", "water": "tidal", "official_url": "https://omurakyotei.jp/suimen/", "forecast_scope": True},
}

# Research alert cutoffs only (NOT empirically fitted to betting performance).
WIND_NOTICE_MPS = 5.0
WIND_STRONG_MPS = 8.0
WAVE_NOTICE_CM = 5.0
WAVE_STRONG_CM = 10.0


def assess_venue(code: str, wind_mps, wave_cm, freshness_status: str, *,
                 relative_wind=None, relative_wind_verified=False,
                 tide_stage=None, tide_verified=False) -> dict:
    """Non-directional advisory; no probabilities, payouts or formal picks."""
    profile = VENUES.get(str(code).zfill(2))
    if profile is None:
        raise ValueError("Unknown BOATRACE venue")
    fresh = freshness_status == "fresh_snapshot"
    signals = []
    alerts = []
    if fresh and isinstance(wind_mps, (int, float)) and not isinstance(wind_mps, bool):
        if wind_mps >= WIND_NOTICE_MPS:
            signals.append("wind_ge_5mps")
            alerts.append("風速5m/s以上：スタートと旋回の変化を確認")
        if wind_mps >= WIND_STRONG_MPS:
            signals.append("wind_ge_8mps")
            alerts.append("強風帯：荒水面・レース運営情報を優先確認")
    if fresh and isinstance(wave_cm, (int, float)) and not isinstance(wave_cm, bool):
        if wave_cm >= WAVE_NOTICE_CM:
            signals.append("wave_ge_5cm")
            alerts.append("波高5cm以上：1・2マークの艇の残り方を確認")
        if wave_cm >= WAVE_STRONG_CM:
            signals.append("wave_ge_10cm")
            alerts.append("高波帯：実際の展示と安定板情報を確認")
    # Monitoring only. A large *candidate* impact never changes formal model,
    # official bets or calibration without pre-cutoff comparative validation.
    # Combined moderate wind and wave may matter even below either severe limit.
    if not fresh:
        candidate = "unavailable"
    elif (isinstance(wind_mps, (int, float)) and not isinstance(wind_mps, bool)
          and wind_mps >= WIND_STRONG_MPS) or (
          isinstance(wave_cm, (int, float)) and not isinstance(wave_cm, bool)
          and wave_cm >= WAVE_STRONG_CM) or (
          isinstance(wind_mps, (int, float)) and not isinstance(wind_mps, bool)
          and isinstance(wave_cm, (int, float)) and not isinstance(wave_cm, bool)
          and wind_mps >= WIND_NOTICE_MPS and wave_cm >= WAVE_NOTICE_CM):
        candidate = "materiality_review"
    elif signals:
        candidate = "caution"
    else:
        candidate = "baseline"
    special = evaluate_special_conditions(
        code, wind_mps, wave_cm, freshness_status,
        relative_wind=relative_wind, relative_wind_verified=relative_wind_verified,
        tide_stage=tide_stage, tide_verified=tide_verified,
    )
    return {
        "schema": "weather_lab.venue_advisory.v1",
        "status": "unavailable" if not fresh else "attention" if signals else "monitor",
        "signals": signals,
        "alerts": alerts,
        "venue_focus": profile["focus"],
        "water_regime": profile["water"],
        "tide_data_needed": profile["water"] == "tidal",
        "tide_stage": None, "tide_current": None,
        "relative_wind_direction": None,
        "wind_direction_source_unmapped": True,
        "prediction_scope": profile["forecast_scope"],
        "official_context_url": profile["official_url"],
        "venue_special_conditions": special,
        "prediction_effect": "none",
        "correction_policy": {
            "role": "supplement_only",
            "model_priority": "athlete_motor_exhibition_entry_tactics_first",
            "candidate_impact": candidate,
            "materiality_is_trained": False,
            "formal_weight_modified": False,
            "automatic_ticket_change": False,
            "needs_mechanism_and_forward_validation": candidate == "materiality_review",
            "note": "気象は選手・機力・展示・艇間展開の補正候補。複合荒水面の大きな影響は検証課題で、現時点では買い目不変。",
        },
        "reason": "研究用の場別監視。勝率や正式買い目には未反映。"
    }
