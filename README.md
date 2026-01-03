# GTA Online Tool

An automated script designed to streamline the recurring cargo acquisition process in GTA Online by leveraging game mechanics and network control.

## Requirements

- Python 3.10+
- uv (Python package installer and virtual environment management tool)
- OS: Windows (Required for `netsh` firewall commands and `pywin32`)

## Installation

1. Clone the repository
```bash
git clone https://github.com/ZerolBozi/gta_tool.git
cd gta_tool
```

2. Create and activate virtual environment using `uv`
```bash
uv venv
source .venv/bin/activate  # For Unix/MacOS
# OR
.venv\Scripts\activate     # For Windows
```

3. Install dependencies using the `pyproject.toml` file:
```bash
uv pip install .
```

## Configuration

You can customize the script's behavior by modifying the `config.toml` file.

 - `[system]` Settings

| Parameter | Default | Description |
| :--- | :--- | :--- |
| `start_time` | `5` | **Startup Delay (Seconds):** The time the script waits after you press Enter. Use this time to bring the GTA V window to the foreground. |
| `execution` | `100` | **Cycles:** The number of times the cargo acquisition loop will run. |
| `join_story` | `6.5` | **Story Mode Cooldown (Seconds):** How long to wait after detecting Story Mode (North Yankton) before restoring the network and starting the next cycle. |
| `transaction_waiting` | `5` | **Transaction Debounce (Seconds):** Sometimes the "Transaction Pending" spinner disappears briefly. The script waits this long to confirm the transaction is truly complete before returning to offline mode. |

- `[keyboard]` Settings

| Parameter | Default | Description |
| :--- | :--- | :--- |
| `hold_time` | `0.1` | **Key Press Duration:** How long a key is held down. Do not set this too high. |
| `wait_time` | `0.55` | **Key Interval:** The delay between keystrokes. Setting this too fast may cause the game to miss inputs or menu errors. |

## Templates & Resolution

The script uses image recognition to detect game states (e.g., Joining Online, Transaction Pending, Story Mode).

- The default templates located in the `templates/` folder are captured at 1920x1080 resolution.

- **Customization:** If your game resolution is different, or if detection fails, you should replace the images in the `templates/` folder with your own screenshots of those specific game states.

## Usage

1. Open **GTA V** and enter **Story Mode**.

2. Run the script as **Administrator** (Required to modify Firewall rules).

```bash
python script.py
```

3. Follow the on-screen prompt: Press `Enter` and immediately switch the GTA V window to the foreground.
