import requests
import jpholiday
import json
import os
import pandas as pd
import dotenv
from datetime import datetime, timezone, timedelta
JST = timezone(timedelta(hours=+9))

def translate_to_en(jp_name: str) -> str:
    df = pd.read_csv('TX_GTFS/translations.txt')
    jp_to_en_dict = df[df['language'] == 'en'].set_index('field_value')['translation'].to_dict()
    return jp_to_en_dict[jp_name]

def get_stop_id(jp_name: str) -> str:
    df = pd.read_csv('TX_GTFS/stops.txt')
    stop_id_dict = df.set_index('stop_name')['stop_id'].to_dict()
    return stop_id_dict[jp_name]
    
def get_arrival_time(ODPT_ACCESS_TOKEN:str, STATION_C_NAME:str, STATION_D_NAME:str, DIRECTION:str) -> tuple[str, str]:
    """
    1. 駅Cの時刻表から最も近い列車を特定
    2. その列車の時刻表から駅Dの到着時刻を直接取得
    """
    df_st: pd.DataFrame= pd.read_csv('TX_GTFS/stop_times.txt')
    # 今日の曜日判定 (0:月曜 ... 5:土曜, 6:日曜)
    now = datetime.now(JST)  # 修正後
    weekday = now.weekday()
    print(f"{now=}")
    if weekday >= 5 or jpholiday.is_holiday(now):
        daytype = "SaturdayHoliday"
    else:
        daytype = "Weekday"

    # --- 1. 駅Cで「今」に最も近い列車を探す ---
    params = {
        "acl:consumerKey": ODPT_ACCESS_TOKEN,
        "odpt:operator":"odpt.Operator:MIR",
        "odpt:station":"odpt.Station:MIR.TsukubaExpress." + translate_to_en(STATION_C_NAME),
        "odpt:calendar":"odpt.Calendar:" + daytype,
        "odpt:railDirection":"odpt.RailDirection:"+ DIRECTION
    }
    Timetable_url = "https://api.odpt.org/api/v4/odpt:StationTimetable" #時刻表
    
    # エラーハンドリング追加
    try:
        res = requests.get(Timetable_url, params).json()
    except Exception as e:
        raise RuntimeError(f"ODPT APIへのリクエストに失敗しました: {e}")
    res: list[dict]

    # for idx in range(len(res)):
    #     for key in res[idx].keys():
    #         if key !="odpt:stationTimetableObject":
    #             print(f"{res[idx][key]=}")
    #     print("=================================================================")

    target_train_id = None
    dep_time_str_nearest = ""
    min_diff = float('inf')

    target_station_d_id = "odpt.Station:MIR.TsukubaExpress." + translate_to_en(STATION_D_NAME)

    # --- Step 1: 直近の電車（列車ID）を特定 ---
    for timetable in res:
        for obj in timetable.get('odpt:stationTimetableObject', []):
            obj:dict
            
            #dep_time_strをdatetimeオブジェクトに変換
            dep_time_str:str = obj['odpt:departureTime'] # "12:30" や "24:15" など
            if not dep_time_str: continue
            try:
                hour, minute = map(int, dep_time_str.split(':'))
            except ValueError:
                continue
            
            train_dt = now.replace(hour=0, minute=0, second=0, microsecond=0)
            if hour >= 24:
                # 24:15 → 翌日の00:15として扱う
                train_dt = train_dt + timedelta(days=1, hours=hour-24, minutes=minute)
            else:
                train_dt = train_dt.replace(hour=hour, minute=minute)
                
            # 日付をまたぐ判定ミスを防ぐため、前後1日を候補に入れる
            candidates = [
                train_dt,
                train_dt - timedelta(days=1), # 昨日
                train_dt + timedelta(days=1)  # 明日
            ]

            # 未来の電車の中で、一番近いものを探す (現在時刻より前の電車は無視)
            # if train_dt < now:
            #     continue

            for cand in candidates:
                # 「今(now)」に最も近い時刻を探す
                diff = abs((cand - now).total_seconds())
                
                if diff < min_diff:
                    min_diff = diff
                    dep_time_str_nearest = dep_time_str
                    target_train_id = obj.get('odpt:train')

    if not target_train_id:
        raise RuntimeError("近い時間の列車が見つかりませんでした。APIのレスポンスや時刻表データを確認してください。")

    print(f"特定した列車ID: {target_train_id}")
    print(f"{STATION_C_NAME}出発時刻：{dep_time_str_nearest}")

    trip_id_suffix = target_train_id.split('.')[-1] #4ケタ
    df_filtered = df_st[df_st['trip_id'].astype(str).str.endswith(trip_id_suffix)].copy()
    
    target_times = [dep_time_str_nearest]
    if dep_time_str_nearest.startswith("00:"):
        target_times.append(dep_time_str_nearest.replace("00:", "24:", 1))
    elif dep_time_str_nearest.startswith("24:"):
        target_times.append(dep_time_str_nearest.replace("24:", "00:", 1))

    # 5. 出発時刻がいずれかに一致する&stop_idが一致するtrip_idを特定
    # departure_timeは秒まで含まれる（24:07:00など）可能性があるため、startswithで判定
    matched_trips = df_filtered[
        (df_filtered['departure_time'].apply(lambda x: any(str(x).startswith(t) for t in target_times))) &
        (df_filtered['stop_id'] == int(get_stop_id(STATION_C_NAME))) 
    ]['trip_id'].unique()

    if len(matched_trips) == 0:
        raise RuntimeError(f"条件に一致する列車が見つかりませんでした。APIのレスポンスや時刻表データを確認してください。{target_times=}")
    
    elif len(matched_trips) > 1:
        print(f"警告: 複数の運行が一致しました。最初の1件を使用します。 {matched_trips}")
    
    final_trip_id = matched_trips[0] #105405みたいな
    result_row = df_st[(df_st['trip_id'] == final_trip_id) & (df_st['stop_id'] == int(get_stop_id(STATION_D_NAME)))]
    print(result_row.iloc[0]['arrival_time'])
    return result_row.iloc[0]['arrival_time'], STATION_D_NAME

# if __name__ == "__main__":
#     arrival_time = get_arrival_time()