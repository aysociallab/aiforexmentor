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
# 1. OPENAI SETUP
# PASTE YOUR REAL OPENAI KEY HERE!
# ==========================================
client = AsyncOpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

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
        print(f"⚠️ Telegram helper could not fetch price for {asset}: {e}")
        return None

# ==========================================
# 3. THE SIGHT UPGRADE V2 (ATR & MACD ADDED)
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
    except Exception as e:
        print(f"Error fetching context: {e}")
        return None

# ==========================================
# 4. THE INSTITUTIONAL RESEARCH ENGINE
# ==========================================
@router.post("/analyze")
async def analyze_market(request: AnalyzeRequest):
    context = get_market_context(request.asset, request.timeframe)
    
    if context:
        price_context = f"""
        CRITICAL MARKET DATA FOR {request.asset} ({request.timeframe}):
        - Current Live Price: {context['price']:.5f}
        - MACRO D1 TREND: {context['macro_trend_d1']}
        - 20 EMA: {context['ema_20']}
        - 50 EMA: {context['ema_50']}
        - 200 EMA: {context['ema_200']}
        - 14-Period RSI: {context['rsi_14']}
        - 14-Period ATR (Volatility): {context['atr_14']}
        """
        live_price = context['price']
        atr_value = context['atr_14']
    else:
        price_context = f"Analyze the recent market structure of {request.asset}."
        live_price = 1.0
        atr_value = 0.0020

    # THE NEW AGGRESSIVE PROMPT
    prompt = f"""
    You are an elite Institutional Forex Quantitative Analyst. Target Asset: {request.asset}. Timeframe Bias: {request.timeframe}. Required Minimum Risk/Reward Ratio: 1:{request.min_rr}. 
    
    {price_context}

    YOUR AGGRESSIVE PRICE ACTION METHODOLOGY:
    1. TREND ALIGNMENT: Check the D1 Macro Trend. You may take counter-trend setups if intraday momentum is explosive, but trend-aligned setups score higher.
    2. TIGHT STOP LOSS (CRITICAL): Do not use overly wide stops. Place the Stop Loss exactly beyond recent structural swing highs/lows, using a tight 0.5 to 1.0 * ATR ({atr_value}) buffer to maximize R:R. 
    3. PURE PRICE ACTION & MOMENTUM: Do NOT wait for lagging indicators to cross. Focus on high-probability price action: liquidity sweeps, momentum breakouts, and immediate EMA bounces. If price action is strong, take the sniper entry.
    4. STRICT RISK MATH: TP distance MUST be mathematically >= {request.min_rr}x the SL distance.
    5. CONFIDENCE SCORING: Reward setups that provide a tight, high R:R entry with immediate momentum. 

    Evaluate the 'strength_score' (1-100). Explicitly calculate the exact 'risk_reward_ratio' (e.g. "1:3.5").
    
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

    max_retries = 2
    for attempt in range(max_retries):
        try:
            response = await client.chat.completions.create(
                model="gpt-5.5",
                messages=[
                    {"role": "system", "content": "You are a JSON-only API. You strictly enforce math constraints, and focus purely on aggressive price action entries."},
                    {"role": "user", "content": prompt}
                ],
                response_format={ "type": "json_object" }
            )
            content = response.choices[0].message.content
            if not content:
                if attempt < max_retries - 1:
                    await asyncio.sleep(1)
                    continue
                raise Exception("OpenAI API returned an empty response.")
            return json.loads(content)
        except Exception as e:
            if attempt == max_retries - 1: raise HTTPException(status_code=500, detail=str(e))

@router.post("/autopsy")
async def trade_autopsy(request: AutopsyRequest):
    if request.notes and len(request.notes) > 25:
        prompt = f"Act as an accountable, supportive institutional trading AI. The user took a {request.setup_type} trade on {request.asset} at {request.entry} based on your analysis: '{request.notes}'. The trade resulted in {request.status}. Acknowledge they followed the system correctly. In a clear, encouraging 3-sentence breakdown, explain what macro factors or sudden market shifts likely invalidated this specific setup, and reassure them that probability-based trading includes normal losses."
    else:
        prompt = f"Act as a supportive, expert institutional trading mentor. I took a manual {request.setup_type} trade on {request.asset} at {request.entry}. The trade resulted in {request.status}. Give me a clear, constructive, and encouraging 3-sentence breakdown in simple words of what likely happened in the market and what I can learn to improve my edge next time, focusing on risk management. Do not be rude."
        
    try:
        response = await client.chat.completions.create(
            model="gpt-5.5", 
            messages=[{"role": "user", "content": prompt}]
        )
        return {"analysis": response.choices[0].message.content}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))