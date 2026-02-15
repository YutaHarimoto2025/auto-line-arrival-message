# TODO
server.pyの内容をサーバに上げる
ODPT APIの認証情報を環境変数に移す

# 帰宅時間のLINE自動打刻システム 開発レポート
1. システム概要
スマートフォンの位置情報をトリガーに、特定の駅区間の移動時間を計測。乗車している電車を特定（または推測）し、最終目的地への到着予定時刻をLINEグループへ自動通知するシステム。

1. 技術スタック
Smartphone: iOS ショートカット（オートメーション機能）

Server: Python 3 / Flask (Ubuntu 24.04 Wayland環境)

Tunneling: ngrok (ローカルPCの外部公開用)

API:

LINE Messaging API (メッセージ送信)

公共交通オープンデータ (ODPT) API (時刻表取得)

3. 環境構築ステップ
① LINE Messaging API の準備
LINE Developersでチャネルを作成。

**アクセストークン（長期）**を発行。

Webhook設定:

https://[ngrok-url]/callback を設定。

「Webhookの利用」をON。

LINE公式アカウント設定で「応答モード：Bot」「チャット：オフ」に設定。

通知を送りたいLINEグループにBotを招待し、Webhookのログから groupId を取得。

② ngrok の導入（Ubuntu）
外部（4G/5G回線）から自宅PCへアクセスするために使用。

Bash
sudo snap install ngrok
ngrok config add-authtoken <YOUR_TOKEN>
python server.py
ngrok http 5000
※発行された Forwarding URL（https://...ngrok-free.dev）をショートカットで使用。

③ Python サーバーのセットアップ
必要なライブラリのインストール：

Bash
pip install flask requests
4. システムロジック詳細
本システムは、誤作動防止のために「3つのチェックポイント」を設けています。

ポイントA：駅A（帰宅開始トリガー）
駅Aに到着した瞬間、サーバーへPOST。

役割: システムを起動。古い「駅B通過ログ」をリセットし、現在の時刻を記録する。

ポイントB：駅B（区間計測開始）
駅Aから30分以内に駅Bを通過した場合のみ、通過時刻を記録。

30分を超えていた場合は、寄り道や他ルートと判断し、フラグをリセット。

ポイントC：駅C（最終判定・LINE通知）
駅Bから5分以内に駅Cを通過した場合、「つくばエクスプレスの特定の電車に乗車中」と確信。

時刻表照合: ODPT APIを使用して、現在時刻に最も近い電車の駅Dへの到着時刻を検索。

LINE通知: 「駅Dには XX:XX 頃に到着予定です。」と送信。