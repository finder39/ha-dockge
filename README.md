# Dockge for Home Assistant

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/hacs/integration)
[![GitHub release](https://img.shields.io/github/release/finder39/ha-dockge.svg)](https://github.com/finder39/ha-dockge/releases/latest)

Home Assistant integration for managing Docker container updates via the [Dockge](https://github.com/finder39/dockge) REST API.

Monitor update availability across all your Docker stacks, toggle auto-updates per stack, and trigger updates — all from within Home Assistant.

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=finder39&repository=ha-dockge&category=integration)

## Features

- **Update monitoring** — per-stack and per-container binary sensors for available image updates
- **Container status** — sensors showing each container's state (running, exited, etc.) with image and health details
- **Auto-update control** — per-stack switches to enable/disable automatic updates
- **Update actions** — buttons to update individual stacks, check for updates, update all, or trigger a scheduled run
- **Scheduler status** — sensor showing auto-update scheduler state, cron expression, and next run times
- **Update history** — sensor tracking the most recent stack update with result details
- **Multi-agent support** — works with multiple Dockge agents, each with their own device hierarchy

## Prerequisites

This integration requires a Dockge instance with the REST API enabled. You will need:

- A running [Dockge](https://github.com/finder39/dockge) instance (fork with REST API and update management)
- An API key configured in Dockge

## Installation

### HACS (Recommended)

1. Open HACS in your Home Assistant instance
2. Click the three dots in the top right and select **Custom repositories**
3. Add `https://github.com/finder39/ha-dockge` with category **Integration**
4. Click **Download** on the Dockge card
5. Restart Home Assistant

Or click the button above to add the repository directly.

### Manual

1. Copy the `custom_components/dockge/` directory to your Home Assistant `custom_components/` folder
2. Restart Home Assistant

## Configuration

1. Go to **Settings > Devices & Services > Add Integration**
2. Search for **Dockge**
3. Enter your Dockge URL (e.g., `http://192.168.1.100:5001`)
4. Enter your API key
5. Optionally adjust the scan interval (default: 30 seconds)

## Entities

### Agent-level (Dockge Server device)

| Type | Entity | Description |
|------|--------|-------------|
| Sensor | Image Updates Available | Count of stacks with available updates |
| Sensor | Auto-Update Scheduler | Scheduler status with cron details |
| Sensor | Last Stack Update | Timestamp of most recent update |
| Sensor | Next Auto Update | Next scheduled auto-update time |
| Sensor | Next Image Check | Next scheduled image check time |
| Button | Update All | Update all stacks across all agents |
| Button | Trigger Scheduled Run | Manually trigger a scheduled update run |

### Stack-level (per stack device)

| Type | Entity | Description |
|------|--------|-------------|
| Binary Sensor | Update Available | On when stack has image updates |
| Binary Sensor | {container} Update Available | On when a specific container has updates |
| Sensor | {container} | Container state with image and health attributes |
| Button | Update | Update this stack |
| Button | Check Updates | Check for new image updates |
| Switch | Auto Update | Enable/disable auto-updates for this stack |

## Vibecoded

This integration was built entirely through vibe coding with [Claude Code](https://claude.ai/claude-code).

## License

MIT
