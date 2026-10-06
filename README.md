<div align="center">

<img src="app/static/img/logo.svg" width="84" alt="ShopMotion logo">

# ShopMotion

**Privacy-first, AI-powered customer behaviour analytics for physical retail stores.**

ShopMotion plugs into a store's existing cameras and turns raw video into clean, easy-to-read insights:
which aisles people visit, which shelves get attention, how long customers stay, and when the store is busiest.

[![CI](https://github.com/musaad-ai/ShopMotion/actions/workflows/ci.yml/badge.svg)](https://github.com/musaad-ai/ShopMotion/actions/workflows/ci.yml)
![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python&logoColor=white)
![Flask](https://img.shields.io/badge/Flask-3.x-000000?logo=flask)
![YOLOv8](https://img.shields.io/badge/YOLOv8-Ultralytics-00FFFF)
![OpenCV](https://img.shields.io/badge/OpenCV-4.x-5C3EE8?logo=opencv)
![License](https://img.shields.io/badge/license-MIT-green)

<img src="docs/screenshots/dashboard.png" alt="ShopMotion dashboard" width="900">

</div>

---

## Table of contents

- [The problem](#the-problem)
- [Features](#features)
- [Screenshots](#screenshots)
- [How it works](#how-it-works)
- [Tech stack](#tech-stack)
- [Getting started](#getting-started)
- [Running with Docker](#running-with-docker)
- [Configuration](#configuration)
- [REST API](#rest-api)
- [Project structure](#project-structure)
- [Testing](#testing)
- [Results](#results)
- [Privacy](#privacy)
- [Author](#author)

## The problem

Most stores only have **sales data**, which tells you what was bought, not what people *looked at*.
There is no simple way to see customer behaviour as it happens: where people walk, where they stop,
and which displays are ignored.

ShopMotion fills that gap. It watches **general movement only**: no faces and no identities, just
anonymous track IDs. It converts that movement into heatmaps, traffic trends, dwell-time metrics and
actionable recommendations.

## Features

| | |
|---|---|
| 🎥 **Live monitoring** | Stream any USB camera, video file or RTSP feed with live bounding boxes, people counts and a detection log |
| 🤖 **AI detection & tracking** | YOLOv8 person detection + DeepSORT multi-object tracking (with automatic OpenCV fallbacks) |
| 🔥 **Heatmaps** | Per-zone visit levels plus a smooth presence-density layer built from where people actually stand |
| ⏱️ **Dwell time** | Average / median / max time per zone, distribution buckets, 7-day trends and engagement ratings |
| 📈 **Traffic analytics** | Hourly, daily, weekly and yearly trends, peak hours, period-over-period comparison |
| 💡 **Automatic insights** | Hottest / underused zones, most common customer path, staffing and layout recommendations |
| 🗺️ **Store layout editor** | Drag-and-drop zones that map straight onto the camera frame |
| 📄 **Reports** | Generate traffic, heatmap, dwell or full summary reports, then view, print or download them as CSV |
| 🚨 **Alerts** | Crowd-threshold alerts with optional email notifications, plus an activity feed |
| 💾 **Recording & snapshots** | Opt-in recording of the annotated feed and one-click JPEG snapshots |
| 🔐 **Security** | Hashed passwords, role-based access (admin / viewer), CSRF protection, safe redirects |
| 🐳 **Deployment** | Docker + Docker Compose with an Nginx reverse proxy, Alembic migrations, GitHub Actions CI |

## Screenshots

<table>
  <tr>
    <td width="50%"><b>Live monitoring</b><br><img src="docs/screenshots/live-monitoring.png" alt="Live monitoring"></td>
    <td width="50%"><b>Traffic analytics</b><br><img src="docs/screenshots/traffic-analytics.png" alt="Traffic analytics"></td>
  </tr>
  <tr>
    <td><b>Heatmap analysis</b><br><img src="docs/screenshots/heatmap.png" alt="Heatmap analysis"></td>
    <td><b>Dwell time analysis</b><br><img src="docs/screenshots/dwell-time.png" alt="Dwell time analysis"></td>
  </tr>
  <tr>
    <td><b>Reports center</b><br><img src="docs/screenshots/reports.png" alt="Reports"></td>
    <td><b>Store layout editor</b><br><img src="docs/screenshots/store-layout.png" alt="Store layout editor"></td>
  </tr>
  <tr>
    <td><b>Camera setup</b><br><img src="docs/screenshots/camera-setup.png" alt="Camera setup"></td>
    <td><b>System settings</b><br><img src="docs/screenshots/settings.png" alt="Settings"></td>
  </tr>
</table>

## How it works

```mermaid
flowchart LR
    A[CCTV / USB camera<br/>Input layer] --> B[VideoProcessor<br/>OpenCV capture]
    B --> C[Detector<br/>YOLOv8 person class]
    C --> D[Tracker<br/>DeepSORT IDs]
    D --> E[BehaviorAnalyzer<br/>zones · dwell · heatmap]
    E --> F[(SQLite<br/>SQLAlchemy ORM)]
    F --> G[Flask REST API]
    G --> H[Dashboard<br/>Chart.js]
    B -. MJPEG stream .-> H
```

1. **Capture**: each enabled camera runs in its own background thread (`app/ai/video_processor.py`).
2. **Detect**: YOLOv8 finds every person in the frame (`app/ai/detector.py`).
3. **Track**: DeepSORT gives each person a stable anonymous ID across frames (`app/ai/tracker.py`).
4. **Analyse**: the *foot point* (bottom-centre of each box) is mapped onto the store zones. Entering or leaving a zone creates a **visit** with its dwell time, and every position is added to the heatmap grid (`app/ai/behavior.py`).
5. **Store**: every few seconds the results are written to the database as traffic samples, visits and heatmap cells.
6. **Visualise**: the dashboard reads aggregated analytics from the REST API (`app/services/analytics.py`).

> No GPU, model weights or camera? ShopMotion still runs. It falls back to OpenCV's HOG people detector
> and a lightweight IoU/centroid tracker, and the `seed-demo` command fills the dashboards with realistic data.

## Tech stack

| Layer | Technology |
|---|---|
| Backend | Python, Flask 3, Flask-Login, Flask-WTF (CSRF), Jinja2 |
| AI / vision | Ultralytics YOLOv8, DeepSORT (`deep-sort-realtime`), OpenCV, NumPy |
| Database | SQLite, SQLAlchemy ORM, Alembic (Flask-Migrate) |
| Frontend | HTML, CSS, JavaScript, Bootstrap 5, Chart.js, Font Awesome |
| DevOps | Docker, Docker Compose, Nginx, Gunicorn, GitHub Actions, pytest |

## Getting started

### Prerequisites

- Python **3.10+**
- *(optional)* a webcam, a video file or an RTSP camera
- *(optional)* an NVIDIA GPU for faster YOLOv8 inference

### Installation

```bash
git clone https://github.com/musaad-ai/ShopMotion.git
cd ShopMotion

python -m venv venv
# Windows: venv\Scripts\activate
source venv/bin/activate

# Core app (OpenCV fallback detector)
pip install -r requirements.txt
# Full AI pipeline: YOLOv8 + DeepSORT (recommended)
pip install -r requirements-ai.txt

cp .env.example .env          # then edit SECRET_KEY
```

### Load demo data and run

```bash
flask --app run.py seed-demo   # 30 days of realistic analytics + demo users
python run.py                  # http://127.0.0.1:5000
```

| Demo account | Password | Role |
|---|---|---|
| `admin` | `admin123` | Admin: cameras, layout, settings, users |
| `viewer` | `viewer123` | Viewer: dashboards, live view, reports |

To start from a clean database instead, skip `seed-demo` and register: **the first account
created automatically becomes the administrator.** You can also run `flask --app run.py create-admin`.

### Connect a camera

Open **Camera Setup**, then either click **Detect Cameras** to find local USB cameras or use **Add Camera** with:

- a device index: `0`, `1`, …
- a video file: `C:\videos\store.mp4` (file playback is paced to the footage's real frame rate)
- a network stream: `rtsp://user:pass@192.168.1.20:554/stream1`

Next, draw your zones in **Store Layout** and press **Start Camera** on **Live Monitoring**.

## Running with Docker

```bash
cp .env.example .env
docker compose up --build        # http://localhost:8080
docker compose exec web flask --app run.py seed-demo
```

Set `INSTALL_AI: "true"` in `docker-compose.yml` to bake YOLOv8 + DeepSORT into the image. Nginx
(`docker/nginx.conf`) serves the static files, adds security headers and disables buffering for the
MJPEG live stream.

## Configuration

All settings come from environment variables or `.env` (see [`.env.example`](.env.example)):

| Variable | Default | Description |
|---|---|---|
| `SECRET_KEY` | `dev-change-me` | Flask session signing key, **change in production** |
| `DATABASE_URL` | `sqlite:///instance/shopmotion.db` | SQLAlchemy database URL |
| `DETECTOR_BACKEND` | `auto` | `auto`, `yolo` or `hog` |
| `TRACKER_BACKEND` | `auto` | `auto`, `deepsort` or `centroid` |
| `YOLO_MODEL` | `yolov8n.pt` | Any Ultralytics model (`yolov8s.pt`, custom weights…) |
| `INFERENCE_EVERY_N_FRAMES` | `2` | Run detection on every Nth frame to save compute |
| `ALLOW_REGISTRATION` | `true` | Allow self sign-up (new users get the *viewer* role) |
| `AUTO_CREATE_TABLES` | `true` | Create tables on start-up; set `false` to rely on Alembic only |
| `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `SMTP_SENDER` | — | Mail server used for email alerts |

Detection confidence, tracking, crowd-alert threshold, recording, email alerts and data retention
can be changed at runtime on the **Settings** page.

Database migrations:

```bash
flask --app run.py db upgrade                     # apply migrations
flask --app run.py db migrate -m "describe change" # after editing models
```

## REST API

Every endpoint requires an authenticated session. State-changing requests need the `X-CSRFToken` header.

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/api/live/start/<camera_id>` | Start a camera pipeline |
| `POST` | `/api/live/stop/<camera_id>` | Stop a camera pipeline |
| `GET` | `/api/live/stream/<camera_id>` | Annotated MJPEG video stream |
| `GET` | `/api/live/detect[/<camera_id>]` | Live counts, FPS and detection log |
| `POST` | `/api/live/snapshot/<camera_id>` | Download the current frame as JPEG |
| `GET` | `/api/analytics/summary` | Dashboard KPIs |
| `GET` | `/api/analytics/traffic?period=today\|week\|month\|year` | Traffic trend, hourly / weekly patterns, comparison, insights (also `start`/`end`) |
| `GET` | `/api/analytics/heatmap?period=…&mode=visits\|dwell` | Zone heat levels, density grid and insights |
| `GET` | `/api/analytics/dwell?period=…` | Dwell-time KPIs, distribution, per-zone stats, recommendations |
| `GET` | `/api/analytics/zones` | Visits per zone and live occupancy |
| `GET` | `/api/system/alerts` | Active alerts (`?all=1` includes resolved) |
| `POST` | `/api/system/alerts/<id>/resolve` | Resolve an alert |
| `GET` `POST` | `/api/system/settings` | Read / update settings *(admin)* |
| `GET` `POST` `PUT` `DELETE` | `/api/system/cameras[/<id>]` | Camera management *(admin for writes)* |
| `GET` `PUT` | `/api/system/zones` | Read / replace the store layout *(admin for writes)* |
| `POST` | `/api/reports` | Generate a report `{type, period}` |
| `GET` | `/api/system/export` | Export all visits as CSV *(admin)* |

Example:

```bash
curl -b cookies.txt "http://127.0.0.1:5000/api/analytics/traffic?period=week"
```

## Project structure

```
ShopMotion/
├── app/
│   ├── ai/                 # Computer-vision pipeline
│   │   ├── detector.py     #   YOLOv8 / HOG person detection
│   │   ├── tracker.py      #   DeepSORT / centroid tracking
│   │   ├── behavior.py     #   zone visits, dwell time, heatmap accumulation
│   │   └── video_processor.py  # camera threads, MJPEG frames, DB flushing
│   ├── api/                # REST endpoints (live, analytics, system)
│   ├── auth/               # login, registration, forms
│   ├── main/               # page routes and admin views
│   ├── services/           # analytics queries, report generation, ingestion
│   ├── static/             # CSS, JavaScript, images
│   ├── templates/          # Jinja2 templates
│   ├── models.py           # SQLAlchemy models
│   ├── seed.py             # default layout + demo data generator
│   └── cli.py              # flask init-db / create-admin / seed-demo
├── docker/                 # Dockerfile + nginx.conf
├── migrations/             # Alembic migrations
├── scripts/                # README screenshot tool
├── tests/                  # pytest suite
├── config.py
├── run.py                  # development server
└── wsgi.py                 # production entry point (gunicorn)
```

## Testing

```bash
pytest
```

The suite (35 tests) covers zone/dwell logic, tracking, authentication and role-based access,
every analytics endpoint, settings validation, camera and layout management, report generation,
and an **end-to-end pipeline test** that feeds a generated video through capture → detection →
tracking → database. CI runs it on Python 3.10, 3.11 and 3.12.

## Results

Measured during the project evaluation (YOLOv8n, RTX 3060, local deployment):

| Metric | Measured | Target | Result |
|---|---|---|---|
| Detection accuracy | 86 % (YOLOv8 validation set) | ≥ 85 % | ✅ Achieved |
| Tracking accuracy (IDF1) | 0.85 | ≥ 0.80 | ✅ Achieved |
| Average frame rate | 13–15 FPS | ≥ 10 FPS | ✅ Achieved |
| Dashboard load time | 1.9 s | ≤ 3 s | ✅ Achieved |
| API response time | < 120 ms (GET) | ≤ 200 ms | ✅ Achieved |
| System uptime | 99.1 % | ≥ 99 % | ✅ Achieved |

## Privacy

ShopMotion is designed to analyse **behaviour, not people**:

- no face recognition and no biometric data; tracks are anonymous numeric IDs that reset
- only aggregated positions, counts and durations are stored; video is saved only if you switch on recording or take a snapshot
- configurable data retention with one-click cleanup of old analytics

Always follow local laws and post clear signage when using camera analytics in a store.

## Author

**Musaad Fahd Alanazi**
College of Applied Sciences, CSIS Department · INFO 312 / COMP 426 Project

## License

Released under the [MIT License](LICENSE).
