#!/usr/bin/env python3
"""
Simple Telegram test script
Tests if your bot can send messages to your group
"""

import os
import requests
import json

def test_telegram():
    """Test Telegram bot functionality"""
    print("🧪 Testing Telegram Bot...")
    
    # Use hardcoded values (same as main script)
    bot_token = "8256148964:AAGtAwiEcLIRMkiLOmPHimWGTBdzmGQOUTc"
    chat_id = "630658837"
    
    print(f"✅ Bot Token: {bot_token[:10]}...")
    print(f"✅ Chat ID: {chat_id}")
    
    # Test 1: Get bot info
    print("\n🔍 Testing bot info...")
    try:
        url = f"https://api.telegram.org/bot{bot_token}/getMe"
        response = requests.get(url, timeout=10)
        
        if response.status_code == 200:
            bot_info = response.json()
            if bot_info.get("ok"):
                bot_name = bot_info["result"]["first_name"]
                bot_username = bot_info["result"]["username"]
                print(f"✅ Bot info retrieved: {bot_name} (@{bot_username})")
            else:
                print(f"❌ Bot info failed: {bot_info}")
                return False
        else:
            print(f"❌ HTTP error: {response.status_code}")
            return False
            
    except Exception as e:
        print(f"❌ Bot info test failed: {e}")
        return False
    
    # Test 2: Send test message
    print("\n📤 Sending test message...")
    try:
        url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        payload = {
            "chat_id": chat_id,
            "text": "🧪 Test message from Delta Spike Notifier\n\nIf you see this, your bot is working correctly! 🎉",
            "parse_mode": "Markdown"
        }
        
        response = requests.post(url, json=payload, timeout=10)
        
        if response.status_code == 200:
            result = response.json()
            if result.get("ok"):
                print("✅ Test message sent successfully!")
                print("📱 Check your Telegram group - you should see the test message")
                return True
            else:
                print(f"❌ Message send failed: {result}")
                return False
        else:
            print(f"❌ HTTP error: {response.status_code}")
            print(f"Response: {response.text}")
            return False
            
    except Exception as e:
        print(f"❌ Message send test failed: {e}")
        return False

def main():
    print("🚀 Telegram Bot Test")
    print("=" * 30)
    
    if test_telegram():
        print("\n🎉 SUCCESS! Your Telegram bot is working correctly.")
        print("\nNext steps:")
        print("1. Run the main notifier: python3 delta_spike_notifier.py")
        print("2. Wait for price spikes to trigger alerts")
        print("3. Check your Telegram group for real-time alerts")
    else:
        print("\n❌ FAILED! Please fix the issues above before running the main notifier.")
        print("\nCommon issues:")
        print("- Bot token is incorrect")
        print("- Chat ID is wrong")
        print("- Bot hasn't been added to your group")
        print("- Bot doesn't have permission to send messages")

if __name__ == "__main__":
    main()
