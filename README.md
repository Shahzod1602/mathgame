# Math Game Telegram Bot

This is a Math Game Telegram Bot where users answer math questions to earn points.

## Features
- **Levels**: School Level (Easy/Medium) and University Level (Calculus, Linear Algebra, Discrete Math).
- **Timer**: 15 seconds for School, 20 seconds for University.
- **Score**: Points are saved in a database (`students` table).
- **Game Over**: If time runs out or wrong answer is given.

## Setup

1. **Install Dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

2. **Get a Bot Token**:
   - Talk to [@BotFather](https://t.me/BotFather) on Telegram.
   - Create a new bot and copy the **API Token**.

3. **Configure the Bot**:
   - Open `math1.py`.
   - Replace `"YOUR_TELEGRAM_BOT_TOKEN"` with your actual token.

4. **Run the Bot**:
   ```bash
   python math1.py
   ```

## Usage
- Start the bot with `/start`.
- Type `/play` to start the game.
- Click the correct answer button within 15 seconds.
