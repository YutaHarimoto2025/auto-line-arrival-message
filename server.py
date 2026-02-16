from flask import Flask, request
from api_line import send_line_meg 
from api_odpt import get_arrival_time
import pandas as pd
import json
import os
import dotenv
import psycopg2
from psycopg2.extras import DictCursor
from datetime import datetime, timedelta, timezone
JST = timezone(timedelta(hours=+9))

app = Flask(__name__)

# JSONファイルのパス
DATA_FILE = "tracking_data.json"
ANYONE = "誰かさん"

dotenv.load_dotenv()
ODPT_ACCESS_TOKEN = os.environ.get("ODPT_ACCESS_TOKEN")
STATION_C_NAME = os.environ.get("STATION_C_NAME")
STATION_D_NAME = os.environ.get("STATION_D_NAME")
DIRECTION = os.environ.get("DIRECTION")

LINE_ACCESS_TOKEN = os.environ.get("LINE_ACCESS_TOKEN")  
LINE_USER_ID = os.environ.get("LINE_USER_ID")

DB_URL = os.environ.get("DB_URL")

def load_data(person: str) -> dict[str, datetime|None]:
    """指定された個人のデータをDBから読み込む。存在しない場合は初期値nullを返す。"""
    conn = psycopg2.connect(DB_URL)
    cur = conn.cursor(cursor_factory=DictCursor)

    try:
        cur.execute("SELECT station_a_time, station_b_time FROM tracking WHERE person = %s;", (person,))
        row = cur.fetchone()
        if row:
            # 存在する場合はそのデータを辞書形式で返す
            return {
                "station_a_time": row["station_a_time"],
                "station_b_time": row["station_b_time"]
            }
        else:
            # 存在しない場合は、新しいユーザーとして null の初期値を返す
            return {"station_a_time": None, "station_b_time": None}
    finally:
        cur.close()
        conn.close()

def save_data(person:str, data:dict[str, datetime|None]) -> None:
    """UPSERT（挿入または更新）を使用して個人のデータを保存する。"""
    conn = psycopg2.connect(DB_URL)
    cur = conn.cursor()

    try:
        # ON CONFLICT (person) により、名前が既に存在すればUPDATE、なければINSERT
        sql = """
        INSERT INTO tracking (person, station_a_time, station_b_time)
        VALUES (%s, %s, %s)
        ON CONFLICT (person) 
        DO UPDATE SET 
            station_a_time = EXCLUDED.station_a_time,
            station_b_time = EXCLUDED.station_b_time;
        """
        cur.execute(sql, (person, data["station_a_time"], data["station_b_time"]))
        
        # 変更を確定
        conn.commit()
        
    except Exception as e:
        conn.rollback()
        print(f"Database save error: {e}")
        raise e
    finally:
        cur.close()
        conn.close()

@app.route('/station_a', methods=['GET'])
def station_a():
    person = request.args.get("person", ANYONE)
    tracking_data = load_data(person)
    tracking_data["station_a_time"] = datetime.now(JST)
    tracking_data["station_b_time"] = None
    save_data(person, tracking_data)
    
    print(f"駅A通過を記録: {tracking_data['station_a_time']}")
    return "Recorded A", 200

@app.route('/station_b', methods=['GET'])
def station_b():
    person = request.args.get("person", ANYONE)
    tracking_data = load_data(person)
    now = datetime.now(JST)
    a_time = tracking_data.get("station_a_time")
    
    if a_time and (now - a_time).total_seconds() / 60 <= 30: #!
        tracking_data["station_b_time"] = now
        save_data(person, tracking_data)
        print(f"駅B通過を記録: {now} (A-B間は30分以内でした)")
        return "Recorded B", 200
    else:
        tracking_data["station_b_time"] = None
        save_data(person, tracking_data)
        print("駅B通過：Aからの時間が経過しすぎているか、Aの記録がありません")
        return "Invalid A-B duration", 200

@app.route('/station_c', methods=['GET'])
def station_c():
    person = request.args.get("person", ANYONE)
    tracking_data = load_data(person)
    now = datetime.now(JST)
    b_time = tracking_data.get("station_b_time")
    
    if b_time:
        duration = (now - b_time).total_seconds() / 60
        print(f"B-C間移動時間: {duration:.1f}分")
        
        if duration <= 5: #!
            arrival_time_str, arrival_station_str = get_arrival_time(ODPT_ACCESS_TOKEN, STATION_C_NAME, STATION_D_NAME, DIRECTION) 
            msg = f"{person}は{arrival_station_str}駅に {arrival_time_str} 頃に到着予定です。"
            send_line_meg(msg, LINE_ACCESS_TOKEN, LINE_USER_ID)
            
            # リセットして保存
            tracking_data["station_a_time"] = None
            tracking_data["station_b_time"] = None
            save_data(person, tracking_data)
            
            return f"Success: {msg}", 200
        else:
            return "Too slow (B-C)", 200
    print("駅C通過：Bの記録がありません")
    return "B time not found or A-B check failed", 400

@app.route('/callback', methods=['GET', 'POST'])
def callback():
    print(request.json)
    return 'OK'

if __name__ == '__main__':
    PORT = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=PORT)