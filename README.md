# Torn Fren

A modular Discord companion bot for [Torn](https://www.torn.com).

## Features

**Current**
- Discord bot with slash commands
- Reusable alert framework
- Travel module (work in progress)

**Planned**
- Travel assistant
- Travel stock tracking
- Profit calculator
- Market tracker
- Organized Crime tools
- Gym planner
- Notification system

## Installation

1. Clone this repository
2. Create a virtual environment: `python -m venv venv`
3. Activate it: `.\venv\Scripts\Activate.ps1` (Windows)
4. Install requirements: `pip install -r requirements.txt`
5. Create a `.env` file in the project root
6. Run the bot: `python run.py`

## Required Environment Variables

```env
DISCORD_BOT_TOKEN=
CHANNEL_ID=
GUILD_ID=
TORN_API_KEY=
```


## Project Structure

- **bot/** owns everything Discord-specific: registering slash commands, sending messages, reading config.
- **modules/** contains game-logic features (travel, market, gym, etc.) with zero knowledge of Discord — they just answer questions.
- **services/** talks to the outside world (Torn API, YATA API) and caches results, so modules don't care where data comes from.
- **data/** holds static config or lookup files that aren't secrets.
- **docs/** is where design decisions and API research live, so they don't get lost in chat history.

## Roadmap

- **v0.1** — Basic Discord bot, slash commands, alert framework
- **v0.2** — Modular architecture, `/travel` command with static data
- **v0.3** — Torn API + YATA API service layer
- **Future** — Real-time travel/market data, Organized Crime tools, gym planner

## License

MIT