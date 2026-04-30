import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from supabase import create_client, Client
import asyncio
import requests
import time
from signals import router as signals_router, get_live_price

app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])
app.include_router(signals_router, prefix="/api/v2")

# ==========================================
# 1. SAAS CONFIGURATION (SECURE CLOUD)
# ==========================================
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")

SUPABASE_URL = os.environ.get("SUPABASE_URL", "https://placeholder.supabase.co")
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_KEY", "placeholder")

try:
    supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
except Exception as e:
    print(f"⚠️ Supabase Init Error (Check Env Vars): {e}")
    supabase = None

def send_telegram_alert(message: str, chat_id: str):
    if not TELEGRAM_BOT_TOKEN or not chat_id:
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": chat_id, "text": message, "parse_mode": "HTML"}
    try:
        requests.post(url, json=payload, timeout=5)
    except Exception as e:
        print(f"⚠️ Telegram Alert Failed for ID {chat_id}: {e}")

# ==========================================
# 2. THE MULTI-TENANT MARKET ENGINE
# ==========================================
async def market_monitoring_heartbeat():
    print("🟢 Multi-Tenant Live Market Engine: ONLINE.")
    
    while True:
        try:
            if not supabase:
                await asyncio.sleep(10)
                continue

            res = supabase.table("trades").select("*").neq("status", "closed_profit").neq("status", "closed_loss").execute()
            active_trades = res.data

            for trade in active_trades:
                trade_id = trade['id']
                user_id = trade['user_id']
                asset = trade['asset']
                setup_type = trade['setup_type'].lower()
                
                user_profile = supabase.table("profiles").select("telegram_chat_id").eq("id", user_id).execute()
                user_chat_id = user_profile.data[0].get('telegram_chat_id') if user_profile.data else None
                
                is_buy = "buy" in setup_type
                is_market = "market" in setup_type
                current_price = get_live_price(asset)
                
                if not current_price: continue
                
                update_data = {}
                is_triggered = trade.get('is_triggered')
                
                if is_market:
                    is_triggered = True
                    
                if not is_triggered:
                    if setup_type == "buy_stop" and current_price >= trade['entry_price']: is_triggered = True
                    elif setup_type == "buy_limit" and current_price <= trade['entry_price']: is_triggered = True
                    elif setup_type == "sell_stop" and current_price <= trade['entry_price']: is_triggered = True
                    elif setup_type == "sell_limit" and current_price >= trade['entry_price']: is_triggered = True
                        
                    if is_triggered:
                        update_data['is_triggered'] = True
                        if user_chat_id: send_telegram_alert(f"🚀 <b>ORDER TRIGGERED!</b>\n\n<b>Asset:</b> {asset}\n<b>Setup:</b> {setup_type.upper().replace('_', ' ')}\n<b>Entry Hit At:</b> {current_price:.5f}", user_chat_id)

                if is_triggered:
                    if is_buy:
                        if current_price >= trade['take_profit_1'] and trade.get('status_tp1') == 'pending':
                            update_data['status_tp1'] = 'hit'
                            update_data['status'] = 'open'
                            update_data['stop_loss'] = trade['entry_price']
                            if user_chat_id: send_telegram_alert(f"💰 <b>TP1 HIT!</b>\n\n<b>Asset:</b> {asset}\n<b>Target:</b> {trade['take_profit_1']:.5f}\n<i>Stop Loss moved to Breakeven.</i>", user_chat_id)
                            
                        if trade.get('take_profit_2') and current_price >= trade['take_profit_2'] and trade.get('status_tp2') == 'pending':
                            update_data['status_tp2'] = 'hit'
                            update_data['status'] = 'open'
                            update_data['stop_loss'] = trade['take_profit_1']
                            if user_chat_id: send_telegram_alert(f"💰💰 <b>TP2 HIT!</b>\n\n<b>Asset:</b> {asset}\n<b>Target:</b> {trade['take_profit_2']:.5f}\n<i>Stop Loss locked at TP1.</i>", user_chat_id)
                            
                        if trade.get('take_profit_3') and current_price >= trade['take_profit_3'] and trade.get('status_tp3') == 'pending':
                            update_data['status_tp3'] = 'hit'
                            update_data['status'] = 'closed_profit'
                            if user_chat_id: send_telegram_alert(f"🏆 <b>FULL TP3 HIT!</b>\n\n<b>Asset:</b> {asset}\n<b>Target:</b> {trade['take_profit_3']:.5f}", user_chat_id)
                            
                        if current_price <= trade['stop_loss']:
                            update_data['status'] = 'closed_loss'
                            if trade.get('status_tp1') == 'pending': update_data['status_tp1'] = 'sl_hit'
                            if trade.get('status_tp2') == 'pending': update_data['status_tp2'] = 'sl_hit'
                            if trade.get('status_tp3') == 'pending': update_data['status_tp3'] = 'sl_hit'
                            if user_chat_id: send_telegram_alert(f"🛑 <b>STOP LOSS HIT!</b>\n\n<b>Asset:</b> {asset}\n<b>Exited At:</b> {trade['stop_loss']:.5f}", user_chat_id)

                    else: 
                        if current_price <= trade['take_profit_1'] and trade.get('status_tp1') == 'pending':
                            update_data['status_tp1'] = 'hit'
                            update_data['status'] = 'open'
                            update_data['stop_loss'] = trade['entry_price']
                            if user_chat_id: send_telegram_alert(f"💰 <b>TP1 HIT!</b>\n\n<b>Asset:</b> {asset}\n<b>Target:</b> {trade['take_profit_1']:.5f}\n<i>Stop Loss moved to Breakeven.</i>", user_chat_id)
                            
                        if trade.get('take_profit_2') and current_price <= trade['take_profit_2'] and trade.get('status_tp2') == 'pending':
                            update_data['status_tp2'] = 'hit'
                            update_data['status'] = 'open'
                            update_data['stop_loss'] = trade['take_profit_1']
                            if user_chat_id: send_telegram_alert(f"💰💰 <b>TP2 HIT!</b>\n\n<b>Asset:</b> {asset}\n<b>Target:</b> {trade['take_profit_2']:.5f}\n<i>Stop Loss locked at TP1.</i>", user_chat_id)
                            
                        if trade.get('take_profit_3') and current_price <= trade['take_profit_3'] and trade.get('status_tp3') == 'pending':
                            update_data['status_tp3'] = 'hit'
                            update_data['status'] = 'closed_profit'
                            if user_chat_id: send_telegram_alert(f"🏆 <b>FULL TP3 HIT!</b>\n\n<b>Asset:</b> {asset}\n<b>Target:</b> {trade['take_profit_3']:.5f}", user_chat_id)
                            
                        if current_price >= trade['stop_loss']:
                            update_data['status'] = 'closed_loss'
                            if trade.get('status_tp1') == 'pending': update_data['status_tp1'] = 'sl_hit'
                            if trade.get('status_tp2') == 'pending': update_data['status_tp2'] = 'sl_hit'
                            if trade.get('status_tp3') == 'pending': update_data['status_tp3'] = 'sl_hit'
                            if user_chat_id: send_telegram_alert(f"🛑 <b>STOP LOSS HIT!</b>\n\n<b>Asset:</b> {asset}\n<b>Exited At:</b> {trade['stop_loss']:.5f}", user_chat_id)

                if update_data:
                    supabase.table("trades").update(update_data).eq("id", trade_id).execute()

        except Exception as e:
            print(f"⚠️ Engine Heartbeat Error: {e}")
        
        await asyncio.sleep(60) 

@app.on_event("startup")
async def startup_event():
    asyncio.create_task(market_monitoring_heartbeat())

@app.get("/")
def read_root():
    return {"status": "AI Forex Mentor API is running securely."}