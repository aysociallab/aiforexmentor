import os
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from openai import AsyncOpenAI
import yfinance as yf
import pandas as pd
import pandas_ta as ta
import json
import asyncio
import time
from typing import Optional

router = APIRouter()

# ==========================================
# 1. OPENAI SETUP (SECURE CLOUD)
# ==========================================
openai_key = os.environ.get("OPENAI_API_KEY", "placeholder")
client = AsyncOpenAI(api_key=openai_key)

class AnalyzeRequest(BaseModel):
    asset: str
    timeframe: str
    min_rr: float

class AutopsyRequest(BaseModel):
    asset: str
    setup_type: str
    entry: float
    status: str
    notes: Optional[str] = "" 

# ==========================================
# 2. GLOBAL LIVE PRICE CACHE
# ==========================================
last_prices = {}
last_fetch_time = 0

@router.get("/live-prices")
async def get_live_prices():
    global last_prices, last_fetch_time
    current_time = time.time()
    
    if current_time - last_fetch_time < 5 and last_prices:
        return last_prices
        
    pairs = ["EURUSD=X", "USDJPY=X", "GBPUSD=X", "USDCAD=X", "AUDUSD=X", "USDCHF=X", "NZDUSD=X", "EURGBP=X", "EURJPY=X", "GBPJPY=X", "GC=F"]
    try:
        data = yf.download(pairs, period="1d", interval="1m", progress=False)
        if not data.empty and 'Close' in data:
            closes = data['Close']
            for pair in pairs:
                clean_name = "XAUUSD" if pair == "GC=F" else pair.replace('=X', '')
                try:
                    last_price = closes[pair].dropna().iloc[-1]
                    last_prices[clean_name] = float(last_price)
                except:
                    pass
        last_fetch_time = current_time
    except Exception as e:
        print(f"Price Fetch Error: {e}")
        
    return last_prices

def get_live_price(asset: str):
    clean_asset = asset.replace('/', '').replace('-', '')
    if clean_asset in last_prices:
        return last_prices[clean_asset]
        
    ticker_symbol = "GC=F" if "XAU" in clean_asset else f"{clean_asset}=X"
    try:
        ticker = yf.Ticker(ticker_symbol)
        todays_data = ticker.history(period='1d', interval='1m')
        if todays_data.empty:
            todays_data = ticker.history(period='5d')
        return float(todays_data['Close'].iloc[-1])
    except Exception as e:
        return None

# ==========================================
# 3. THE SIGHT UPGRADE V2
# ==========================================
def get_market_context(asset: str, timeframe: str):
    clean_asset = asset.replace('/', '').replace('-', '')
    ticker_symbol = "GC=F" if "XAU" in clean_asset else f"{clean_asset}=X"
    
    if "intraday" in timeframe.lower():
        period = "1mo"
        interval = "1h"
    else:
        period = "1y"
        interval = "1d"
        
    try:
        ticker = yf.Ticker(ticker_symbol)
        df = ticker.history(period=period, interval=interval)
        
        df_daily = ticker.history(period="6mo", interval="1d")
        df_daily.ta.ema(length=50, append=True)
        macro_trend = "Bullish" if float(df_daily['Close'].iloc[-1]) > float(df_daily['EMA_50'].iloc[-1]) else "Bearish"

        if df.empty: return None
            
        df.ta.ema(length=20, append=True)
        df.ta.ema(length=50, append=True)
        df.ta.ema(length=200, append=True)
        df.ta.rsi(length=14, append=True)
        df.ta.atr(length=14, append=True)
        df.ta.macd(fast=12, slow=26, signal=9, append=True)
        
        latest = df.iloc[-1]
        
        return {
            "price": float(latest['Close']),
            "macro_trend_d1": macro_trend,
            "ema_20": float(latest['EMA_20']) if not pd.isna(latest['EMA_20']) else "N/A",
            "ema_50": float(latest['EMA_50']) if not pd.isna(latest['EMA_50']) else "N/A",
            "ema_200": float(latest['EMA_200']) if not pd.isna(latest['EMA_200']) else "N/A",
            "rsi_14": float(latest['RSI_14']) if not pd.isna(latest['RSI_14']) else "N/A",
            "atr_14": float(latest['ATRr_14']) if not pd.isna(latest['ATRr_14']) else 0.0010,
            "macd_hist": float(latest['MACDh_12_26_9']) if not pd.isna(latest['MACDh_12_26_9']) else 0.0
        }
    except Exception:
        return None

# ==========================================
# 4. THE INSTITUTIONAL RESEARCH ENGINE
# ==========================================
@router.post("/analyze")
async def analyze_market(request: AnalyzeRequest):
    context = get_market_context(request.asset, request.timeframe)
    if context:
        price_context = f"Live Price: {context['price']:.5f}. D1 Trend: {context['macro_trend_d1']}. 20 EMA: {context['ema_20']}. 50 EMA: {context['ema_50']}. 200 EMA: {context['ema_200']}. RSI: {context['rsi_14']}. ATR: {context['atr_14']}"
        live_price = context['price']
        atr_value = context['atr_14']
    else:
        price_context = f"Analyze market structure of {request.asset}."
        live_price = 1.0
        atr_value = 0.0020

    prompt = f"""
    You are an elite Quant. Asset: {request.asset}. Bias: {request.timeframe}. Min R/R: 1:{request.min_rr}. 
    {price_context}
    RULES: 1. Align with D1 Trend. 2. SL MUST be 0.5 to 1.0 * ATR ({atr_value}) away from entry. 3. Pure aggressive price action. No lagging indicator wait times. 4. Strict math: TP distance >= {request.min_rr}x SL distance.
    Calculate strength_score (1-100) and risk_reward_ratio ("1:X").
    Respond ONLY in valid JSON:
    {{
        "market_buy": {{ "strength_score": 85, "risk_reward_ratio": "1:3.5", "entry": {live_price}, "stop_loss": 0.0, "take_profit_1": 0.0, "take_profit_2": 0.0, "take_profit_3": 0.0, "deep_analysis": "..." }},
        "market_sell": {{ "strength_score": 0, "risk_reward_ratio": "1:0", "entry": 0.0, "stop_loss": 0.0, "take_profit_1": 0.0, "take_profit_2": 0.0, "take_profit_3": 0.0, "deep_analysis": "..." }},
        "buy_stop": {{ "strength_score": 0, "risk_reward_ratio": "1:0", "entry": 0.0, "stop_loss": 0.0, "take_profit_1": 0.0, "take_profit_2": 0.0, "take_profit_3": 0.0, "deep_analysis": "..." }},
        "sell_stop": {{ "strength_score": 0, "risk_reward_ratio": "1:0", "entry": 0.0, "stop_loss": 0.0, "take_profit_1": 0.0, "take_profit_2": 0.0, "take_profit_3": 0.0, "deep_analysis": "..." }},
        "buy_limit": {{ "strength_score": 0, "risk_reward_ratio": "1:0", "entry": 0.0, "stop_loss": 0.0, "take_profit_1": 0.0, "take_profit_2": 0.0, "take_profit_3": 0.0, "deep_analysis": "..." }},
        "sell_limit": {{ "strength_score": 0, "risk_reward_ratio": "1:0", "entry": 0.0, "stop_loss": 0.0, "take_profit_1": 0.0, "take_profit_2": 0.0, "take_profit_3": 0.0, "deep_analysis": "..." }}
    }}
    """
    try:
        response = await client.chat.completions.create(model="gpt-5.5", messages=[{"role": "system", "content": "You are a JSON API. Focus purely on aggressive price action."}, {"role": "user", "content": prompt}], response_format={ "type": "json_object" })
        return json.loads(response.choices[0].message.content)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/autopsy")
async def trade_autopsy(request: AutopsyRequest):
    prompt = f"Act as an accountable, supportive trading AI. I took a {request.setup_type} trade on {request.asset} at {request.entry}. Result: {request.status}. Give a 3-sentence encouraging breakdown of what market factors invalidated this setup, focusing on risk management. Do not be rude."
    try:
        response = await client.chat.completions.create(model="gpt-5.5", messages=[{"role": "user", "content": prompt}])
        return {"analysis": response.choices[0].message.content}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))