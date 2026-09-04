# simulate.py
# Stand-in for what Tampermonkey will eventually send.
# Knows nothing about Discord — just represents detected game state.

target = "Jogger"
status = "Walking"

if __name__ == "__main__":
    print(f"Detected target: {target} ({status})")