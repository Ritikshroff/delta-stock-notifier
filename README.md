# Delta Spike Notifier

A real-time cryptocurrency spike detector that monitors Delta Exchange for significant price movements and sends alerts via Telegram.

## Features

- **Real-time monitoring** of top trading pairs by volume
- **Smart spike detection** using multiple indicators
- **Telegram notifications** with detailed analysis
- **24/7 monitoring** when deployed on Render

## Deployment on Render

This project is configured for easy deployment on Render.com:

1. **Fork this repository** to your GitHub account
2. **Connect to Render** and create a new Web Service
3. **Select your forked repository**
4. **Use these settings:**
   - Build Command: `pip install -r requirements.txt`
   - Start Command: `python final.py`
   - Plan: Free

## Configuration

The script uses hardcoded Telegram credentials and is ready to run without additional setup.

## How It Works

1. Connects to Delta Exchange WebSocket
2. Monitors top 120 trading pairs by volume
3. Analyzes 15-minute price movements
4. Sends Telegram alerts when spikes are detected
5. Includes cooldown periods to prevent spam

## Alert Criteria

- **Price Change**: 2% in 15 minutes
- **Volume**: Above $5,000 turnover
- **Score Threshold**: 0.65
- **Cooldown**: 15 minutes per symbol

## Files

- `final.py` - Main application
- `requirements.txt` - Python dependencies
- `render.yaml` - Render deployment configuration
- `Procfile` - Process configuration
- `runtime.txt` - Python version specification