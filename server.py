from flask import Flask, request
import datetime
from api_line import send_line_meg 
from api_odpt import get_arrival_time
import pandas as pd
import json
import os
import dotenv

app = Flask(__name__)

# JSONファイルのパス
DATA_FILE = "tracking_data.json"
df_st: pd.DataFrame= pd.read_csv('TX_GTFS/stop_times.txt') #重いので一度だけ読み込む
dotenv.load_dotenv()
ODPT_ACCESS_TOKEN = os.getenv("ODPT_ACCESS_TOKEN")
STATION_C_NAME = os.getenv("STATION_C_NAME")
STATION_D_NAME = os.getenv("STATION_D_NAME")
DIRECTION = os.getenv("DIRECTION")

LINE_ACCESS_TOKEN = os.getenv("LINE_ACCESS_TOKEN")  
LINE_USER_ID = os.getenv("LINE_USER_ID")

def save_data(data):
    """データをJSONファイルに保存するヘルパー関数"""
    # datetimeオブジェクトはそのままではJSONにできないので文字列に変換
    serializable_data = {
        "station_a_time": data["station_a_time"].isoformat() if data["station_a_time"] else None,
        "station_b_time": data["station_b_time"].isoformat() if data["station_b_time"] else None
    }
    with open(DATA_FILE, "w") as f:
        json.dump(serializable_data, f)

def load_data():
    """データをJSONファイルから読み込むヘルパー関数"""
    if not os.path.exists(DATA_FILE):
        return {"station_a_time": None, "station_b_time": None}
    
    with open(DATA_FILE, "r") as f:
        raw_data = json.load(f)
    
    # 文字列をdatetimeオブジェクトに戻す
    return {
        "station_a_time": datetime.datetime.fromisoformat(raw_data["station_a_time"]) if raw_data["station_a_time"] else None,
        "station_b_time": datetime.datetime.fromisoformat(raw_data["station_b_time"]) if raw_data["station_b_time"] else None
    }

@app.route('/station_a', methods=['GET', 'POST'])
def station_a():
    # ファイルから最新の状態を読み込み、更新して保存
    tracking_data = load_data()
    tracking_data["station_a_time"] = datetime.datetime.now()
    tracking_data["station_b_time"] = None
    save_data(tracking_data)
    
    print(f"駅A通過を記録: {tracking_data['station_a_time']}")
    return "Recorded A", 200

@app.route('/station_b', methods=['GET', 'POST'])
def station_b():
    now = datetime.datetime.now()
    tracking_data = load_data() # ファイルから読み込み
    a_time = tracking_data.get("station_a_time")
    
    if a_time and (now - a_time).total_seconds() / 60 <= 30:
        tracking_data["station_b_time"] = now
        save_data(tracking_data) # 更新を保存
        print(f"駅B通過を記録: {now} (A-B間は30分以内でした)")
        return "Recorded B", 200
    else:
        tracking_data["station_b_time"] = None
        save_data(tracking_data)
        print("駅B通過：Aからの時間が経過しすぎているか、Aの記録がありません")
        return "Invalid A-B duration", 200

@app.route('/station_c', methods=['GET', 'POST'])
def station_c():
    now = datetime.datetime.now()
    tracking_data = load_data() # ファイルから読み込み
    b_time = tracking_data.get("station_b_time")
    
    if request.method == 'POST' and request.is_json:
        person = request.json.get("person", "誰かさん")
    else:
        person = request.args.get("person", "誰かさん")
    
    if b_time:
        duration = (now - b_time).total_seconds() / 60
        print(f"B-C間移動時間: {duration:.1f}分")
        
        if duration <= 5:
            arrival_time_str, arrival_station_str = get_arrival_time(df_st, ODPT_ACCESS_TOKEN, STATION_C_NAME, STATION_D_NAME, DIRECTION) 
            msg = f"{person}は{arrival_station_str}駅に {arrival_time_str} 頃に到着予定です。"
            send_line_meg(msg, LINE_ACCESS_TOKEN, LINE_USER_ID)
            
            # リセットして保存
            tracking_data["station_a_time"] = None
            tracking_data["station_b_time"] = None
            save_data(tracking_data)
            
            return f"Success: {msg}", 200
        else:
            return "Too slow (B-C)", 200
    
    return "B time not found or A-B check failed", 400

@app.route('/callback', methods=['GET', 'POST'])
def callback():
    print(request.json)
    return 'OK'

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)