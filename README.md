# BLE Proximity Chat

A modern desktop messaging application built with Python and PyQt6 that uses Bluetooth Low Energy (BLE) to communicate with nearby devices.

## Features
- **Offline Messaging**: Chat without Wi-Fi or Cellular Data using BLE.
- **Modern UI**: Clean, responsive interface powered by PyQt6.
- **Background Scanning**: Discover nearby users automatically.
- **Database Storage**: Full chat history saved locally using SQLite.

## Installation

1. Make sure you have Python 3.9+ installed and Bluetooth enabled on your Windows 10/11 device.
2. Install the required dependencies:
   ```bash
   pip install -r requirements.txt
   ```

## Running the App

To start the application, run:
```bash
python main.py
```

## How to Use
1. **Device Name:** Your device will automatically generate a random user ID and broadcast its presence.
2. **Find Friends:** Click the **"📡 Nearby"** button on the top left sidebar to open the scanning window.
3. **Connect:** Once a friend's device is discovered, select them and click **Connect**.
4. **Chat:** A new chat session will appear in your sidebar. Click it to start sending messages!

**Note:** BLE GATT operation on Windows can sometimes be restrictive. Ensure that Windows Bluetooth Settings are open and pairable if devices struggle to see your BLE Server instance.
