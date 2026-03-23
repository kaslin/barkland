# Barkland — A Multi-Agent Dog Simulation System

## Technical Design Document v2

**Version:** 2.0  
**Date:** March 23, 2026  
**Author:** Tomer  
**Status:** Draft — Ready for Design Review

---

## 1. Overview

Barkland is a multi-agent simulation engine where each dog runs as an autonomous ADK (Google Agent Development Kit) agent powered by **Gemini Flash**. Dogs have quirky, jealous, funny personalities expressed through **translated barks** — the LLM generates what each dog is "really saying" as they go about their day. A finite state machine governs behavior (Sleep, Play, Eat), while Gemini brings each dog to life with personality.

The system ships with a **web UI** for watching the simulation unfold in real time, and runs on **Kubernetes via agent-sandbox** from day one.

### 1.1 Goals

- Each dog is a Gemini Flash–powered ADK `Agent` with a unique personality and bark voice
- FSM handles state transitions (deterministic, testable); Gemini handles personality expression (bark translations, reactions, jealousy)
- Web UI: watch dogs in real time, see bark translations, start/stop simulation, configure dog count
- Food is abundant — this is a feel-good simulation, not a survival game
- Runs in agent-sandbox on GKE from day one
- Simple JSON event log for all simulation output

### 1.2 Non-Goals (V1)

- No breeding, aging, or death lifecycle
- No persistent storage between simulation runs
- No real-time user interaction with individual dogs mid-simulation (just start/stop/observe)
- No audio or image generation

---

## 2. Architecture

### 2.1 High-Level Component Diagram

```
┌──────────────────────────────────────────────────────────────────┐
│                         Barkland System                          │
│                                                                  │
│  ┌────────────┐    ┌───────────────────────────────────────┐     │
│  │  Web UI    │◀──▶│          FastAPI Backend               │     │
│  │  (React)   │ WS │  /api/start  /api/stop  /ws/stream    │     │
│  └────────────┘    └──────────────┬────────────────────────┘     │
│                                   │                              │
│                    ┌──────────────▼──────────────────────┐       │
│                    │     SimulationOrchestrator          │       │
│                    │     (ADK LoopAgent + Runner)        │       │
│                    └──────────────┬──────────────────────┘       │
│                                   │                              │
│              ┌────────────────────┼────────────────────┐         │
│              ▼                    ▼                    ▼          │
│       ┌─────────────┐     ┌─────────────┐     ┌─────────────┐   │
│       │  DogAgent   │     │  DogAgent   │     │  DogAgent   │   │
│       │  "Buddy"    │     │  "Luna"     │     │  "Max"      │   │
│       │             │     │             │     │             │   │
│       │ ┌─────────┐ │     │ ┌─────────┐ │     │ ┌─────────┐ │   │
│       │ │  FSM    │ │     │ │  FSM    │ │     │ │  FSM    │ │   │
│       │ └─────────┘ │     │ └─────────┘ │     │ └─────────┘ │   │
│       │ ┌─────────┐ │     │ ┌─────────┐ │     │ ┌─────────┐ │   │
│       │ │ Gemini  │ │     │ │ Gemini  │ │     │ │ Gemini  │ │   │
│       │ │ Flash   │ │     │ │ Flash   │ │     │ │ Flash   │ │   │
│       │ └─────────┘ │     │ └─────────┘ │     │ └─────────┘ │   │
│       └─────────────┘     └─────────────┘     └─────────────┘   │
│              │                    │                    │          │
│              └────────────────────┼────────────────────┘          │
│                                   ▼                              │
│                    ┌──────────────────────────┐                  │
│                    │   ParkEnvironment        │                  │
│                    │   (Shared Session State)  │                  │
│                    └──────────────────────────┘                  │
└──────────────────────────────────────────────────────────────────┘

             Deployed inside agent-sandbox pod on GKE
```

### 2.2 Component Responsibilities

| Component | Role |
|---|---|
| **Web UI** | React SPA — watch simulation, read bark translations, start/stop, set dog count |
| **FastAPI Backend** | REST endpoints for control + WebSocket for real-time event streaming |
| **SimulationOrchestrator** | ADK `LoopAgent` that advances ticks, triggers all dogs per tick |
| **DogAgent** | ADK `LlmAgent` (Gemini Flash) with FSM tools — personality + state logic |
| **ParkEnvironment** | Shared ADK session state — play invitations, dog snapshots, event log |

---

## 3. The Hybrid Model: FSM + Gemini Flash

### 3.1 Why Hybrid?

The FSM handles **what** the dog does (sleep, eat, play). Gemini Flash handles **how** the dog talks about it. This gives us:

- **Deterministic behavior**: State transitions are testable and reproducible
- **Creative expression**: Each dog has a unique voice, jealousy, humor, personality
- **Cost efficiency**: Gemini Flash is cheap and fast — one short call per dog per tick
- **Separation of concerns**: FSM logic is unit-testable without LLM; bark generation is independently tunable

### 3.2 How It Works Per Tick

```
For each dog, each tick:

  1. FSM evaluates needs → determines next state (pure Python, no LLM)
  2. State + context packaged into a prompt for Gemini Flash
  3. Gemini Flash generates a "bark translation" — what the dog is thinking/saying
  4. Both the state change AND the bark are emitted as events
```

### 3.3 DogAgent — ADK LlmAgent with Tools

Each `DogAgent` is an ADK `LlmAgent` backed by `gemini-2.0-flash`. The FSM logic is exposed as **tools** the agent can call, and the agent's **instruction** defines its personality.

```python
# Pseudocode — architecture, not final code
from google.adk.agents import Agent

def create_dog_agent(name: str, breed: str, personality: str) -> Agent:
    return Agent(
        name=name,
        model="gemini-2.0-flash",
        instruction=f"""You are {name}, a {breed} in Barkland dog park.

Your personality: {personality}

Every tick, you will receive your current state (sleeping/eating/playing),
your needs (energy, hunger, boredom), and what other dogs are doing.

You MUST call the `tick_update` tool to advance your state.
Then respond with a short, funny "bark translation" — what you're
REALLY thinking right now. Keep it 1-2 sentences max.

Rules for your bark translations:
- You are a dog. Think like a dog. Talk like a dog who got subtitles.
- Be jealous when others play without you
- Be dramatic about food ("finally, SUSTENANCE")
- Be grumpy when woken up
- Reference other dogs by name — you have opinions about them
- Keep it PG and hilarious
""",
        tools=[tick_update, get_park_status],
    )
```

### 3.4 Personality Templates

Dogs are generated with randomized personality archetypes:

| Archetype | Traits | Example Bark |
|---|---|---|
| **The Drama Queen** | Overreacts to everything, jealous, theatrical | *"Oh GREAT, Luna gets to play and I'm here STARVING. This is the WORST day of my life. Again."* |
| **The Philosopher** | Deep thoughts about kibble, existential naps | *"As I eat, I wonder… does the kibble enjoy being eaten? Are we so different, the kibble and I?"* |
| **The Gossip** | Comments on everyone, knows all the drama | *"Did you SEE Buddy sleeping AGAIN? That's his third nap. Some of us have standards."* |
| **The Jock** | Obsessed with play, competitive, high energy | *"PLAY TIME PLAY TIME let's GO who wants to RACE I'm gonna WIN"* |
| **The Foodie** | Lives for meals, rates every bite, food snob | *"Hmm, today's kibble has notes of chicken with a hint of… more chicken. Adequate. 7/10."* |
| **The Grump** | Hates being disturbed, sarcastic, secretly sweet | *"If one more dog tries to play with me before I've finished my nap, I swear to Dog…"* |

Each simulation assigns personalities randomly from this pool, ensuring variety.

---

## 4. State Machine (FSM Layer)

### 4.1 State Definitions

| State | Description | ~Target % | Need Effects Per Tick |
|---|---|---|---|
| `SLEEPING` | Dog is asleep. Energy recharges, hunger slowly builds | ~60% | energy +8, hunger +2, boredom +1 |
| `EATING` | Dog eats from the always-available food bowl | ~15% | energy -1, hunger -10, boredom +2 |
| `PLAYING` | Dog plays with a partner. Burns energy, cures boredom | ~25% | energy -5, hunger +3, boredom -8 |

### 4.2 State Transition Rules

```
SLEEPING → exit when:
    energy >= 90 AND (hunger > 70 → EATING, boredom > 60 → PLAYING)
    If both hunger and boredom are moderate, weighted random with sleep bias

EATING → exit when:
    hunger < 20 → evaluate: energy < 30 → SLEEPING, boredom > 50 → PLAYING, else SLEEPING

PLAYING → exit when:
    energy < 30 → SLEEPING
    hunger > 80 → EATING
    partner left → re-evaluate
```

### 4.3 Food is Abundant

Food is **not** a scarce resource. The food bowl is always full. Dogs eat when hungry and always succeed. This keeps the simulation lighthearted and removes starvation edge cases. The `EATING` state exists for variety and pacing, not survival.

### 4.4 The 60% Sleep Guarantee

Achieved through need dynamics tuning:

- Energy drains fast during play (-5/tick) and slowly during eating (-1/tick)
- Energy recharges at +8/tick during sleep, but the exit threshold is high (>=90)
- Sleep entry threshold is generous (<30 energy)
- Net effect: dogs spend ~8-12 ticks sleeping per cycle, ~3-5 eating, ~4-6 playing
- Validated by e2e tests asserting average sleep in [55%, 65%] range

### 4.5 Play Partner Matching

```
Phase 1: All dogs that want to play post to a shared invitation list
Phase 2: Resolver matches pairs in FIFO order
         - Even count: all paired
         - Odd count: last dog stays in current state (generates a lonely bark)
Phase 3: Paired dogs enter PLAYING, linked by partner name
         - If one partner exits, other gets notified next tick
```

---

## 5. Orchestration with ADK

### 5.1 Agent Hierarchy

```
SimulationOrchestrator (LoopAgent — repeats for N ticks)
  └── TickRunner (SequentialAgent — one tick cycle)
        ├── Phase1_Decide (ParallelAgent)
        │     ├── DogAgent "Buddy"   ──▶ FSM tool call → state decision
        │     ├── DogAgent "Luna"    ──▶ FSM tool call → state decision
        │     └── DogAgent "Max"     ──▶ FSM tool call → state decision
        │
        ├── Phase2_Resolve (Custom BaseAgent)
        │     └── Match play partners, apply state transitions
        │
        └── Phase3_Express (ParallelAgent)
              ├── DogAgent "Buddy"   ──▶ Gemini Flash → bark translation
              ├── DogAgent "Luna"    ──▶ Gemini Flash → bark translation
              └── DogAgent "Max"     ──▶ Gemini Flash → bark translation
```

**Why 3 phases?**

- **Phase 1 (Parallel)**: Dogs evaluate needs independently — no ordering dependency, no LLM call yet
- **Phase 2 (Sequential)**: Single resolver handles play matching — prevents race conditions
- **Phase 3 (Parallel)**: All dogs generate bark translations simultaneously — this is where Gemini Flash is called, with full context of what just happened

### 5.2 Gemini Flash Context Per Bark

Each bark generation call includes:

```
You are {name} the {breed}. Personality: {personality_description}

Current tick: {tick}
Your state: {state} (just transitioned from {prev_state})
Your needs: energy={energy}, hunger={hunger}, boredom={boredom}
Your play partner: {partner_name or "none"}

Other dogs right now:
- Luna: PLAYING with Rocky (boredom=12, having a blast)
- Max: SLEEPING (energy=22, been out for 6 ticks)
- Daisy: EATING (hunger=65, on her second bowl)

What just happened:
- You woke up from a nap and decided to eat
- Luna and Rocky started playing without you

Generate your bark translation (1-2 sentences, funny, in character):
```

---

## 6. Web UI

### 6.1 Layout

```
┌─────────────────────────────────────────────────────────────┐
│  🐾 BARKLAND                              [▶ Start] [⏹ Stop] │
│  Dogs: [  5  ▾]  Ticks: [ 200 ▾]  Speed: [●●●○○]           │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  Tick 47 / 200                                    🍖 Food: ∞ │
│  ═══════════════════════════════════════════════             │
│                                                             │
│  ┌─────────────────────────────────────────────────────┐    │
│  │ 💤 Buddy (Golden Retriever) — SLEEPING              │    │
│  │ Energy: ████████░░ 78   Hunger: ██░░░░░░░░ 23       │    │
│  │ Boredom: █████░░░░░ 48                              │    │
│  │                                                     │    │
│  │ 🗨️ "zzZZzz... I was chasing the BIGGEST squirrel... │    │
│  │    tell Luna to keep it down out there..."          │    │
│  └─────────────────────────────────────────────────────┘    │
│                                                             │
│  ┌─────────────────────────────────────────────────────┐    │
│  │ 🎾 Luna (Husky) — PLAYING with Rocky               │    │
│  │ Energy: ██████░░░░ 55   Hunger: ████░░░░░░ 41       │    │
│  │ Boredom: ██░░░░░░░░ 15                              │    │
│  │                                                     │    │
│  │ 🗨️ "I am FASTER than you Rocky and we BOTH know it. │    │
│  │    Also Buddy is missing OUT."                      │    │
│  └─────────────────────────────────────────────────────┘    │
│                                                             │
│  ┌─────────────────────────────────────────────────────┐    │
│  │ 🍗 Max (French Bulldog) — EATING                    │    │
│  │ Energy: ████████░░ 72   Hunger: ███████░░░ 68       │    │
│  │ Boredom: ███░░░░░░░ 29                              │    │
│  │                                                     │    │
│  │ 🗨️ "This kibble is slightly warmer than yesterday's. │    │
│  │    Chef's kiss. Would pair well with a nap."        │    │
│  └─────────────────────────────────────────────────────┘    │
│                                                             │
├─────────────────────────────────────────────────────────────┤
│  📜 Event Log                                    [Clear]    │
│  ─────────────────────────────────────────────────────────  │
│  T47: Max started eating                                   │
│  T46: Luna and Rocky started playing                       │
│  T45: Buddy fell asleep                                    │
│  T44: Rocky woke up — "FINALLY. Who wants to PLAY?"        │
│  T43: Luna stopped eating — "That was mid at best."        │
└─────────────────────────────────────────────────────────────┘
```

### 6.2 UI Components

| Component | Description |
|---|---|
| **Control Bar** | Start/Stop buttons, dog count selector (1-20), tick count, simulation speed slider |
| **Tick Counter** | Current tick / total, progress bar |
| **Dog Cards** | One card per dog: name, breed, state icon, need bars, latest bark translation |
| **Event Log** | Scrollable reverse-chronological feed of state changes and notable barks |

### 6.3 Tech Stack

| Layer | Technology |
|---|---|
| Frontend | React (single-page app, served by FastAPI static files) |
| Styling | Tailwind CSS |
| Real-time | WebSocket (`/ws/stream`) — server pushes tick events as JSON |
| Backend | FastAPI (async, serves both API and static frontend) |
| State | In-memory — no database for V1 |

### 6.4 API Endpoints

```
POST /api/simulation/start
  Body: { "num_dogs": 5, "num_ticks": 200, "speed_ms": 1000 }
  Response: { "simulation_id": "uuid", "dogs": [...] }

POST /api/simulation/stop
  Response: { "status": "stopped", "ticks_completed": 47 }

GET  /api/simulation/status
  Response: { "running": true, "tick": 47, "dogs": [...] }

WS   /ws/stream
  Server pushes per tick:
  {
    "tick": 47,
    "dogs": [
      {
        "name": "Buddy",
        "breed": "Golden Retriever",
        "state": "sleeping",
        "energy": 78,
        "hunger": 23,
        "boredom": 48,
        "bark": "zzZZzz... tell Luna to keep it down...",
        "play_partner": null,
        "personality": "grump"
      },
      ...
    ],
    "events": [
      {"dog": "Max", "type": "state_change", "from": "playing", "to": "eating"}
    ]
  }
```

### 6.5 Simulation Speed Control

The `speed_ms` parameter controls the delay between ticks (default: 1000ms = 1 tick/second). The UI slider maps to:

| Label | Delay | Use Case |
|---|---|---|
| 🐢 Slow | 2000ms | Read every bark carefully |
| 🐕 Normal | 1000ms | Default watching speed |
| 🐇 Fast | 500ms | Skim through quickly |
| ⚡ Turbo | 100ms | Stress test / bulk run |

---

## 7. Project Structure

```
barkland/
├── pyproject.toml
├── Dockerfile
├── README.md
├── .env                             # GOOGLE_GENAI_USE_VERTEXAI, API keys
│
├── barkland/
│   ├── __init__.py
│   ├── main.py                      # FastAPI app entry point
│   ├── config.py                    # SimulationConfig dataclass
│   │
│   ├── agents/
│   │   ├── __init__.py
│   │   ├── dog_agent.py             # DogAgent — LlmAgent with personality + FSM tools
│   │   ├── orchestrator.py          # SimulationOrchestrator — LoopAgent setup
│   │   ├── resolver.py              # Phase2 conflict resolver (play matching)
│   │   └── personalities.py         # Personality templates and randomizer
│   │
│   ├── models/
│   │   ├── __init__.py
│   │   ├── dog.py                   # DogState enum, DogNeeds, DogProfile
│   │   ├── park.py                  # ParkEnvironment state schema
│   │   └── events.py               # SimulationEvent, TickSnapshot
│   │
│   ├── engine/
│   │   ├── __init__.py
│   │   ├── fsm.py                   # DogStateMachine — pure transition logic
│   │   ├── needs.py                 # Need update functions per state
│   │   └── matching.py              # Play partner matching algorithm
│   │
│   ├── api/
│   │   ├── __init__.py
│   │   ├── routes.py                # REST endpoints: start, stop, status
│   │   └── websocket.py             # WebSocket handler for /ws/stream
│   │
│   └── output/
│       ├── __init__.py
│       ├── logger.py                # JSON event logger (writes .json files)
│       └── stats.py                 # Post-simulation summary stats
│
├── frontend/
│   ├── index.html                   # SPA shell
│   ├── src/
│   │   ├── App.jsx                  # Main React app
│   │   ├── components/
│   │   │   ├── ControlBar.jsx       # Start/Stop, dog count, speed
│   │   │   ├── DogCard.jsx          # Individual dog display
│   │   │   ├── DogGrid.jsx          # Grid of all dog cards
│   │   │   ├── EventLog.jsx         # Scrollable event feed
│   │   │   ├── NeedBar.jsx          # Animated progress bar
│   │   │   └── TickProgress.jsx     # Tick counter + progress
│   │   ├── hooks/
│   │   │   └── useSimulation.js     # WebSocket hook + state management
│   │   └── utils/
│   │       └── constants.js         # State icons, colors, breed list
│   └── package.json
│
├── tests/
│   ├── unit/
│   │   ├── test_fsm.py              # FSM transition correctness
│   │   ├── test_needs.py            # Need clamping, delta calculations
│   │   ├── test_matching.py         # Play partner matching edge cases
│   │   ├── test_personalities.py    # Personality assignment + uniqueness
│   │   └── test_config.py           # Config validation
│   │
│   ├── integration/
│   │   ├── test_dog_agent.py        # Single dog agent lifecycle with Gemini mock
│   │   ├── test_orchestrator.py     # Full tick cycle with multiple dogs
│   │   ├── test_play_protocol.py    # Two dogs play interaction
│   │   └── test_api.py              # FastAPI endpoint tests
│   │
│   └── e2e/
│       ├── test_simulation.py       # Full run, assert 60% sleep ratio
│       ├── test_websocket.py        # WS stream delivers correct events
│       └── test_determinism.py      # Same seed → same FSM transitions
│
├── k8s/
│   ├── sandbox-template.yaml        # SandboxTemplate for Barkland pod
│   ├── sandbox-claim.yaml           # SandboxClaim for on-demand runs
│   └── warm-pool.yaml               # WarmPool for fast startup
│
└── scripts/
    ├── build.sh                     # Docker build + push
    └── deploy.sh                    # kubectl apply sandbox manifests
```

---

## 8. Data Models

### 8.1 Core Types

```python
from enum import Enum
from dataclasses import dataclass, field
from typing import Optional
import random

class DogState(Enum):
    SLEEPING = "sleeping"
    EATING = "eating"
    PLAYING = "playing"

class Personality(Enum):
    DRAMA_QUEEN = "drama_queen"
    PHILOSOPHER = "philosopher"
    GOSSIP = "gossip"
    JOCK = "jock"
    FOODIE = "foodie"
    GRUMP = "grump"

@dataclass
class DogNeeds:
    energy: float = field(default_factory=lambda: random.uniform(40, 80))
    hunger: float = field(default_factory=lambda: random.uniform(20, 50))
    boredom: float = field(default_factory=lambda: random.uniform(30, 60))

    def clamp(self):
        self.energy = max(0.0, min(100.0, self.energy))
        self.hunger = max(0.0, min(100.0, self.hunger))
        self.boredom = max(0.0, min(100.0, self.boredom))

@dataclass
class DogProfile:
    name: str
    breed: str
    personality: Personality
    state: DogState = DogState.SLEEPING
    needs: DogNeeds = field(default_factory=DogNeeds)
    play_partner: Optional[str] = None
    ticks_in_state: int = 0
    latest_bark: str = ""

@dataclass
class SimulationConfig:
    num_dogs: int = 5
    num_ticks: int = 200
    speed_ms: int = 1000           # delay between ticks in milliseconds
    seed: int = 42
    log_file: Optional[str] = None # path to write JSON event log
```

### 8.2 Tick Snapshot (WebSocket Payload)

```python
@dataclass
class DogSnapshot:
    name: str
    breed: str
    personality: str
    state: str
    energy: float
    hunger: float
    boredom: float
    bark: str                       # Gemini-generated bark translation
    play_partner: Optional[str]

@dataclass
class TickEvent:
    dog: str
    event_type: str                 # "state_change" | "play_start" | "play_end"
    from_state: Optional[str] = None
    to_state: Optional[str] = None
    detail: Optional[str] = None

@dataclass
class TickSnapshot:
    tick: int
    total_ticks: int
    dogs: list[DogSnapshot]
    events: list[TickEvent]
```

### 8.3 JSON Event Log Format

One JSON object per line, appended per tick:

```json
{"tick": 47, "timestamp": "2026-03-23T10:15:32Z", "dogs": [{"name": "Buddy", "state": "sleeping", "energy": 78.0, "hunger": 23.0, "boredom": 48.0, "bark": "zzZZzz... tell Luna to keep it down...", "play_partner": null}], "events": [{"dog": "Max", "type": "state_change", "from": "playing", "to": "eating"}]}
```

---

## 9. FSM Implementation

### 9.1 Transition Logic (Pure Function — No LLM)

```python
def evaluate_transition(
    dog: DogProfile,
    play_invitations: list[str],
    rng: random.Random
) -> DogState:
    """
    Determine the next state. Pure function, no side effects, no LLM.
    Food is always available — no scarcity check needed.
    """
    if dog.state == DogState.SLEEPING:
        if dog.needs.energy >= 90:
            if dog.needs.hunger > 70:
                return DogState.EATING
            if dog.needs.boredom > 60 and len(play_invitations) > 0:
                return DogState.PLAYING
            if dog.needs.hunger > 50 or dog.needs.boredom > 40:
                choices = [DogState.EATING, DogState.PLAYING, DogState.SLEEPING]
                weights = [dog.needs.hunger, dog.needs.boredom, 50]
                return rng.choices(choices, weights=weights, k=1)[0]
        return DogState.SLEEPING

    elif dog.state == DogState.EATING:
        if dog.needs.hunger < 20:
            if dog.needs.energy < 30:
                return DogState.SLEEPING
            if dog.needs.boredom > 50:
                return DogState.PLAYING
            return DogState.SLEEPING
        return DogState.EATING

    elif dog.state == DogState.PLAYING:
        if dog.needs.energy < 30:
            return DogState.SLEEPING
        if dog.needs.hunger > 80:
            return DogState.EATING
        return DogState.PLAYING

    return dog.state
```

### 9.2 Need Deltas (Per Tick)

```python
NEED_DELTAS = {
    DogState.SLEEPING: {"energy": +8, "hunger": +2, "boredom": +1},
    DogState.EATING:   {"energy": -1, "hunger": -10, "boredom": +2},
    DogState.PLAYING:  {"energy": -5, "hunger": +3, "boredom": -8},
}
```

---

## 10. Gemini Flash Integration

### 10.1 Bark Generation Tool

```python
def generate_bark_context(dog: DogProfile, park_state: dict, tick: int) -> str:
    """Build the context string sent to Gemini Flash for bark generation."""
    others = []
    for name, info in park_state["dog_states"].items():
        if name != dog.name:
            partner_str = f" with {info['play_partner']}" if info.get("play_partner") else ""
            others.append(f"- {name}: {info['state'].upper()}{partner_str}")

    return f"""Tick {tick}. You are {dog.state.value}.
Energy: {dog.needs.energy:.0f}/100, Hunger: {dog.needs.hunger:.0f}/100, Boredom: {dog.needs.boredom:.0f}/100.
Partner: {dog.play_partner or 'none'}.

Other dogs:
{chr(10).join(others)}

Generate a funny 1-2 sentence bark translation. Stay in character as a {dog.personality.value}."""
```

### 10.2 Personality Instructions (Agent System Prompt)

```python
PERSONALITY_INSTRUCTIONS = {
    Personality.DRAMA_QUEEN: """You overreact to EVERYTHING. A nap interrupted is a TRAGEDY.
Someone playing without you is BETRAYAL. Food is either the BEST or WORST thing ever.
Use caps for emphasis. Be theatrical and jealous.""",

    Personality.PHILOSOPHER: """You find deep meaning in mundane dog activities.
Eating kibble triggers existential reflection. Naps are journeys of the soul.
Playing is a metaphor for the fleeting nature of joy. Be contemplative and weird.""",

    Personality.GOSSIP: """You are obsessed with what other dogs are doing.
You comment on everyone's choices. You judge sleeping patterns.
You have opinions about who plays with whom. Be nosy and opinionated.""",

    Personality.JOCK: """You are ALL about playing. Everything is a competition.
You count your play streaks. Sleeping is just recovery for more playing.
Eating is fuel for WINNING. Be hyper and competitive.""",

    Personality.FOODIE: """You rate every meal. You describe kibble like a wine sommelier.
You have a refined palate. You are disappointed when meals end.
Other activities are just things between meals. Be pretentious about food.""",

    Personality.GRUMP: """You hate being disturbed. You tolerate other dogs at best.
You complain about everything but secretly enjoy company.
Sarcastic, dry humor. Short sentences. Eye-rolling energy.""",
}
```

### 10.3 Cost Estimate

| Scenario | Dogs | Ticks | Gemini Calls | Est. Tokens | Est. Cost |
|---|---|---|---|---|---|
| Quick demo | 5 | 50 | 250 | ~75K | ~$0.01 |
| Standard run | 5 | 200 | 1,000 | ~300K | ~$0.04 |
| Large run | 20 | 500 | 10,000 | ~3M | ~$0.40 |

Gemini 2.0 Flash pricing makes this negligible even for extended runs.

---

## 11. Deployment: agent-sandbox on GKE

### 11.1 SandboxTemplate

```yaml
apiVersion: agents.x-k8s.io/v1alpha1
kind: SandboxTemplate
metadata:
  name: barkland-runtime
  namespace: default
spec:
  template:
    spec:
      containers:
        - name: barkland
          image: gcr.io/<PROJECT_ID>/barkland:latest
          resources:
            requests:
              cpu: "500m"
              memory: "512Mi"
            limits:
              cpu: "2"
              memory: "2Gi"
          ports:
            - containerPort: 8000    # FastAPI
          env:
            - name: GOOGLE_GENAI_USE_VERTEXAI
              value: "TRUE"
            - name: GOOGLE_CLOUD_PROJECT
              valueFrom:
                fieldRef:
                  fieldPath: metadata.namespace
      runtimeClassName: gvisor
```

### 11.2 WarmPool

```yaml
apiVersion: agents.x-k8s.io/v1alpha1
kind: SandboxWarmPool
metadata:
  name: barkland-pool
  namespace: default
spec:
  sandboxTemplateName: barkland-runtime
  minReady: 2
  maxSize: 10
```

### 11.3 Dockerfile

```dockerfile
FROM python:3.12-slim

WORKDIR /app

# Install Node.js for frontend build
RUN apt-get update && apt-get install -y nodejs npm && rm -rf /var/lib/apt/lists/*

# Backend dependencies
COPY pyproject.toml .
RUN pip install --no-cache-dir .

# Frontend build
COPY frontend/ frontend/
RUN cd frontend && npm install && npm run build

# Application code
COPY barkland/ barkland/

# Serve frontend static files from FastAPI
RUN cp -r frontend/dist barkland/static

EXPOSE 8000
CMD ["uvicorn", "barkland.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

### 11.4 Local Development (via Tunnel Mode)

```python
from k8s_agent_sandbox import SandboxClient

# For local dev — tunnels to sandbox pod via kubectl port-forward
with SandboxClient(
    template_name="barkland-runtime",
    namespace="default"
) as sandbox:
    result = sandbox.run("curl http://localhost:8000/api/simulation/status")
    print(result.stdout)
```

---

## 12. Dependencies

```toml
[project]
name = "barkland"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = [
    "google-adk>=1.0.0",
    "google-genai",               # Gemini Flash access
    "fastapi>=0.115.0",
    "uvicorn[standard]>=0.30.0",
    "websockets>=12.0",
    "pydantic>=2.0",
]

[project.optional-dependencies]
sandbox = [
    "k8s-agent-sandbox",
]
dev = [
    "pytest>=8.0",
    "pytest-asyncio",
    "pytest-cov",
    "httpx",                      # FastAPI test client
    "ruff",
    "mypy",
]
```

---

## 13. Testing Strategy

### 13.1 Testing Philosophy

The testing strategy is built on three pillars:

1. **FSM logic is pure and fully unit-testable** — no LLM, no network, no shared state. Every transition path is covered with deterministic inputs.
2. **Gemini is always mocked below e2e** — unit and integration tests never hit the real API. Bark generation is behind a clean interface that can be swapped for a fake.
3. **E2E tests validate the system as a user sees it** — start simulation via API, read events from WebSocket, assert on statistical properties (sleep ratio, state coverage) and schema correctness.

### 13.2 Test Pyramid & Coverage Targets

```
                    ┌───────────┐
                    │   E2E     │   ~10 tests    — real API, real WS, optional live Gemini
                    │  (slow)   │   Target: critical user flows
                    ├───────────┤
                    │Integration│   ~20 tests    — multi-component, Gemini mocked
                    │ (medium)  │   Target: agent lifecycle, API contracts, tick pipeline
                    ├───────────┤
                    │   Unit    │   ~60 tests    — single function, pure logic
                    │  (fast)   │   Target: every FSM path, every edge case
                    └───────────┘

Coverage target: 90%+ on barkland/engine/*, 80%+ on barkland/agents/*, 75%+ overall
```

### 13.3 Test Configuration

```python
# conftest.py (root)

import pytest
import random

def pytest_addoption(parser):
    parser.addoption(
        "--live-llm", action="store_true", default=False,
        help="Run e2e tests against real Gemini Flash (requires API key)"
    )
    parser.addoption(
        "--slow", action="store_true", default=False,
        help="Run slow performance/stress tests"
    )

@pytest.fixture
def seeded_rng():
    """Deterministic RNG for reproducible FSM tests."""
    return random.Random(42)

@pytest.fixture
def default_config():
    """Standard simulation config for tests."""
    return SimulationConfig(num_dogs=5, num_ticks=100, seed=42, speed_ms=0)
```

### 13.4 Gemini Mock Strategy

All Gemini interactions go through a single `BarkGenerator` interface. Tests swap the real implementation for a fake.

```python
# barkland/agents/bark_generator.py

from abc import ABC, abstractmethod

class BarkGenerator(ABC):
    @abstractmethod
    async def generate(self, dog: DogProfile, context: str) -> str:
        """Generate a bark translation for the given dog and tick context."""
        ...

class GeminiBarkGenerator(BarkGenerator):
    """Production: calls Gemini 2.0 Flash."""
    async def generate(self, dog: DogProfile, context: str) -> str:
        # Real Gemini call via ADK LlmAgent
        ...

class FakeBarkGenerator(BarkGenerator):
    """Test double: returns deterministic barks based on state."""
    async def generate(self, dog: DogProfile, context: str) -> str:
        return f"[{dog.name}] Fake bark while {dog.state.value}"
```

```python
# conftest.py

@pytest.fixture
def fake_bark_generator():
    return FakeBarkGenerator()

@pytest.fixture
def mock_gemini_response():
    """Patch the Gemini model call at the ADK level."""
    with patch("google.adk.models.gemini.GeminiLlm.generate") as mock:
        mock.return_value = MockLlmResponse(text="Woof! (test bark)")
        yield mock
```

**Key rule**: `FakeBarkGenerator` is used for unit and integration tests. `GeminiBarkGenerator` is only used in e2e tests gated behind `--live-llm`.

---

### 13.5 Unit Tests — Detailed Test Cases

All unit tests are **fast** (<100ms each), **deterministic**, and **isolated** (no network, no disk, no shared state).

#### 13.5.1 `test_fsm.py` — State Transition Logic

```python
class TestSleepingTransitions:
    """Tests for dogs currently in SLEEPING state."""

    def test_stays_asleep_low_energy(self, seeded_rng):
        """Dog with low energy stays asleep regardless of hunger/boredom."""
        dog = make_dog(state=SLEEPING, energy=50, hunger=90, boredom=90)
        assert evaluate_transition(dog, [], seeded_rng) == DogState.SLEEPING

    def test_wakes_to_eat_high_hunger(self, seeded_rng):
        """Dog with full energy and high hunger transitions to eating."""
        dog = make_dog(state=SLEEPING, energy=95, hunger=75, boredom=20)
        assert evaluate_transition(dog, [], seeded_rng) == DogState.EATING

    def test_wakes_to_play_high_boredom_partner_available(self, seeded_rng):
        """Dog with full energy, high boredom, and available partner transitions to playing."""
        dog = make_dog(state=SLEEPING, energy=95, hunger=20, boredom=65)
        assert evaluate_transition(dog, ["Luna"], seeded_rng) == DogState.PLAYING

    def test_wakes_to_play_no_partner_stays_asleep_or_eats(self, seeded_rng):
        """Dog with high boredom but no play partner does NOT transition to playing."""
        dog = make_dog(state=SLEEPING, energy=95, hunger=20, boredom=65)
        result = evaluate_transition(dog, [], seeded_rng)
        assert result != DogState.PLAYING

    def test_energy_exactly_90_triggers_evaluation(self, seeded_rng):
        """Boundary: energy=90 is the exit threshold."""
        dog = make_dog(state=SLEEPING, energy=90, hunger=75, boredom=20)
        assert evaluate_transition(dog, [], seeded_rng) == DogState.EATING

    def test_energy_89_stays_asleep(self, seeded_rng):
        """Boundary: energy=89 is below exit threshold."""
        dog = make_dog(state=SLEEPING, energy=89, hunger=99, boredom=99)
        assert evaluate_transition(dog, [], seeded_rng) == DogState.SLEEPING

    def test_moderate_needs_uses_weighted_random(self, seeded_rng):
        """When hunger and boredom are moderate, result is probabilistic but seeded."""
        dog = make_dog(state=SLEEPING, energy=95, hunger=55, boredom=45)
        results = [evaluate_transition(dog, ["X"], random.Random(s)) for s in range(100)]
        states = set(results)
        assert len(states) >= 2  # Should produce variety across different seeds

    def test_hunger_priority_over_boredom_when_both_high(self, seeded_rng):
        """When both hunger and boredom are critical, hunger > 70 takes priority."""
        dog = make_dog(state=SLEEPING, energy=95, hunger=80, boredom=80)
        assert evaluate_transition(dog, ["X"], seeded_rng) == DogState.EATING


class TestEatingTransitions:
    """Tests for dogs currently in EATING state."""

    def test_stays_eating_still_hungry(self, seeded_rng):
        dog = make_dog(state=EATING, energy=50, hunger=60, boredom=30)
        assert evaluate_transition(dog, [], seeded_rng) == DogState.EATING

    def test_stops_eating_full_goes_to_sleep(self, seeded_rng):
        """Dog that's full and not bored defaults to sleeping."""
        dog = make_dog(state=EATING, energy=50, hunger=15, boredom=30)
        assert evaluate_transition(dog, [], seeded_rng) == DogState.SLEEPING

    def test_stops_eating_full_goes_to_play_if_bored(self, seeded_rng):
        """Dog that's full but bored transitions to playing."""
        dog = make_dog(state=EATING, energy=50, hunger=15, boredom=55)
        assert evaluate_transition(dog, [], seeded_rng) == DogState.PLAYING

    def test_stops_eating_full_low_energy_goes_to_sleep(self, seeded_rng):
        """Dog that's full, bored, but exhausted → sleep wins."""
        dog = make_dog(state=EATING, energy=20, hunger=15, boredom=55)
        assert evaluate_transition(dog, [], seeded_rng) == DogState.SLEEPING

    def test_hunger_exactly_20_exits_eating(self, seeded_rng):
        """Boundary: hunger=20 triggers exit."""
        dog = make_dog(state=EATING, energy=50, hunger=20, boredom=30)
        # hunger < 20 is the condition, so hunger=20 should stay eating
        assert evaluate_transition(dog, [], seeded_rng) == DogState.EATING

    def test_hunger_19_exits_eating(self, seeded_rng):
        """Boundary: hunger=19 triggers exit."""
        dog = make_dog(state=EATING, energy=50, hunger=19, boredom=30)
        assert evaluate_transition(dog, [], seeded_rng) != DogState.EATING


class TestPlayingTransitions:
    """Tests for dogs currently in PLAYING state."""

    def test_stays_playing_healthy(self, seeded_rng):
        dog = make_dog(state=PLAYING, energy=60, hunger=40, boredom=30)
        assert evaluate_transition(dog, [], seeded_rng) == DogState.PLAYING

    def test_stops_playing_exhausted(self, seeded_rng):
        dog = make_dog(state=PLAYING, energy=25, hunger=40, boredom=30)
        assert evaluate_transition(dog, [], seeded_rng) == DogState.SLEEPING

    def test_stops_playing_starving(self, seeded_rng):
        dog = make_dog(state=PLAYING, energy=60, hunger=85, boredom=30)
        assert evaluate_transition(dog, [], seeded_rng) == DogState.EATING

    def test_energy_exactly_30_keeps_playing(self, seeded_rng):
        """Boundary: energy=30 does NOT trigger sleep (condition is < 30)."""
        dog = make_dog(state=PLAYING, energy=30, hunger=40, boredom=30)
        assert evaluate_transition(dog, [], seeded_rng) == DogState.PLAYING

    def test_energy_29_triggers_sleep(self, seeded_rng):
        dog = make_dog(state=PLAYING, energy=29, hunger=40, boredom=30)
        assert evaluate_transition(dog, [], seeded_rng) == DogState.SLEEPING

    def test_exhausted_and_starving_sleep_wins(self, seeded_rng):
        """When both energy < 30 and hunger > 80, energy is checked first → sleep."""
        dog = make_dog(state=PLAYING, energy=20, hunger=90, boredom=10)
        assert evaluate_transition(dog, [], seeded_rng) == DogState.SLEEPING


class TestAllStatesTransitions:
    """Cross-cutting transition tests."""

    def test_every_state_has_at_least_one_exit(self, seeded_rng):
        """No state is a dead end — every state can transition to at least one other."""
        for state in DogState:
            exits = set()
            for energy in range(0, 101, 10):
                for hunger in range(0, 101, 10):
                    for boredom in range(0, 101, 10):
                        dog = make_dog(state=state, energy=energy, hunger=hunger, boredom=boredom)
                        result = evaluate_transition(dog, ["Partner"], seeded_rng)
                        exits.add(result)
            assert len(exits) >= 2, f"{state} can never exit"
```

#### 13.5.2 `test_needs.py` — Need Update Logic

```python
class TestNeedDeltas:
    """Verify need changes per state are applied correctly."""

    @pytest.mark.parametrize("state,field,expected_delta", [
        (DogState.SLEEPING, "energy", +8),
        (DogState.SLEEPING, "hunger", +2),
        (DogState.SLEEPING, "boredom", +1),
        (DogState.EATING, "energy", -1),
        (DogState.EATING, "hunger", -10),
        (DogState.EATING, "boredom", +2),
        (DogState.PLAYING, "energy", -5),
        (DogState.PLAYING, "hunger", +3),
        (DogState.PLAYING, "boredom", -8),
    ])
    def test_delta_applied_correctly(self, state, field, expected_delta):
        dog = make_dog(state=state, energy=50, hunger=50, boredom=50)
        update_needs(dog)
        assert getattr(dog.needs, field) == 50 + expected_delta


class TestNeedClamping:
    """Verify needs stay within [0, 100] bounds."""

    def test_energy_clamped_at_100(self):
        dog = make_dog(state=SLEEPING, energy=98)
        update_needs(dog)  # +8 → 106 → clamped to 100
        assert dog.needs.energy == 100.0

    def test_energy_clamped_at_0(self):
        dog = make_dog(state=PLAYING, energy=3)
        update_needs(dog)  # -5 → -2 → clamped to 0
        assert dog.needs.energy == 0.0

    def test_hunger_clamped_at_0(self):
        dog = make_dog(state=EATING, hunger=5)
        update_needs(dog)  # -10 → -5 → clamped to 0
        assert dog.needs.hunger == 0.0

    def test_all_needs_stay_in_bounds_after_1000_ticks(self):
        """Stress: apply random state transitions for 1000 ticks, needs always in [0,100]."""
        rng = random.Random(99)
        dog = make_dog(state=SLEEPING, energy=50, hunger=50, boredom=50)
        for _ in range(1000):
            dog.state = rng.choice(list(DogState))
            update_needs(dog)
            assert 0 <= dog.needs.energy <= 100
            assert 0 <= dog.needs.hunger <= 100
            assert 0 <= dog.needs.boredom <= 100
```

#### 13.5.3 `test_matching.py` — Play Partner Matching

```python
class TestPlayMatching:

    def test_two_dogs_paired(self):
        pairs, unmatched = match_play_partners(["Buddy", "Luna"])
        assert pairs == [("Buddy", "Luna")]
        assert unmatched == []

    def test_four_dogs_two_pairs(self):
        pairs, unmatched = match_play_partners(["A", "B", "C", "D"])
        assert len(pairs) == 2
        assert unmatched == []

    def test_odd_dogs_one_unmatched(self):
        pairs, unmatched = match_play_partners(["A", "B", "C"])
        assert len(pairs) == 1
        assert len(unmatched) == 1

    def test_single_dog_no_match(self):
        pairs, unmatched = match_play_partners(["Buddy"])
        assert pairs == []
        assert unmatched == ["Buddy"]

    def test_empty_list(self):
        pairs, unmatched = match_play_partners([])
        assert pairs == []
        assert unmatched == []

    def test_large_group_all_matched(self):
        dogs = [f"Dog{i}" for i in range(20)]
        pairs, unmatched = match_play_partners(dogs)
        assert len(pairs) == 10
        assert unmatched == []

    def test_no_dog_appears_in_two_pairs(self):
        dogs = [f"Dog{i}" for i in range(10)]
        pairs, _ = match_play_partners(dogs)
        all_dogs = [d for pair in pairs for d in pair]
        assert len(all_dogs) == len(set(all_dogs))  # no duplicates

    def test_fifo_order_deterministic(self):
        """First dog in list pairs with second, third with fourth, etc."""
        pairs, _ = match_play_partners(["A", "B", "C", "D"])
        assert pairs[0] == ("A", "B")
        assert pairs[1] == ("C", "D")
```

#### 13.5.4 `test_personalities.py` — Personality Assignment

```python
class TestPersonalityAssignment:

    def test_unique_personalities_up_to_pool_size(self):
        """With 6 dogs and 6 archetypes, all should be different."""
        dogs = assign_personalities(6, random.Random(42))
        personalities = [d.personality for d in dogs]
        assert len(set(personalities)) == 6

    def test_personalities_cycle_when_more_dogs_than_archetypes(self):
        """With 8 dogs and 6 archetypes, at least 2 will repeat but spread evenly."""
        dogs = assign_personalities(8, random.Random(42))
        from collections import Counter
        counts = Counter(d.personality for d in dogs)
        assert max(counts.values()) - min(counts.values()) <= 1

    def test_single_dog_gets_personality(self):
        dogs = assign_personalities(1, random.Random(42))
        assert dogs[0].personality in Personality

    def test_personality_is_seeded(self):
        """Same seed → same assignment."""
        a = assign_personalities(5, random.Random(42))
        b = assign_personalities(5, random.Random(42))
        assert [d.personality for d in a] == [d.personality for d in b]
```

#### 13.5.5 `test_config.py` — Configuration Validation

```python
class TestSimulationConfig:

    def test_valid_config(self):
        cfg = SimulationConfig(num_dogs=5, num_ticks=100)
        assert cfg.num_dogs == 5

    def test_zero_dogs_raises(self):
        with pytest.raises(ValueError, match="num_dogs"):
            SimulationConfig(num_dogs=0, num_ticks=100)

    def test_negative_dogs_raises(self):
        with pytest.raises(ValueError):
            SimulationConfig(num_dogs=-3, num_ticks=100)

    def test_zero_ticks_raises(self):
        with pytest.raises(ValueError, match="num_ticks"):
            SimulationConfig(num_dogs=5, num_ticks=0)

    def test_negative_speed_raises(self):
        with pytest.raises(ValueError):
            SimulationConfig(num_dogs=5, num_ticks=100, speed_ms=-1)

    def test_dogs_exceeds_name_pool(self):
        """More dogs than available names → should still work (appends numbers)."""
        cfg = SimulationConfig(num_dogs=25, num_ticks=100)
        assert cfg.num_dogs == 25

    def test_max_dogs_cap(self):
        """System caps at 20 dogs for V1."""
        with pytest.raises(ValueError, match="maximum"):
            SimulationConfig(num_dogs=50, num_ticks=100)
```

---

### 13.6 Integration Tests — Multi-Component Flows

Integration tests verify that components work together correctly. Gemini is always mocked. Each test runs in <5 seconds.

#### 13.6.1 `test_dog_agent.py` — Single Agent Lifecycle

```python
class TestDogAgentLifecycle:

    @pytest.mark.asyncio
    async def test_agent_runs_20_ticks(self, fake_bark_generator):
        """Single dog agent processes 20 ticks without errors."""
        agent = create_dog_agent("Buddy", "Golden Retriever", Personality.GRUMP)
        agent.bark_generator = fake_bark_generator

        for tick in range(20):
            result = await agent.process_tick(tick, park_state={})
            assert result.state in DogState
            assert isinstance(result.bark, str)
            assert len(result.bark) > 0

    @pytest.mark.asyncio
    async def test_state_transitions_are_valid(self, fake_bark_generator):
        """Every transition follows an allowed FSM path."""
        agent = create_dog_agent("Luna", "Husky", Personality.JOCK)
        agent.bark_generator = fake_bark_generator
        VALID_TRANSITIONS = {
            DogState.SLEEPING: {DogState.SLEEPING, DogState.EATING, DogState.PLAYING},
            DogState.EATING:   {DogState.EATING, DogState.SLEEPING, DogState.PLAYING},
            DogState.PLAYING:  {DogState.PLAYING, DogState.SLEEPING, DogState.EATING},
        }

        prev_state = agent.dog.state
        for tick in range(50):
            result = await agent.process_tick(tick, park_state={})
            assert result.state in VALID_TRANSITIONS[prev_state], \
                f"Invalid transition: {prev_state} → {result.state} at tick {tick}"
            prev_state = result.state

    @pytest.mark.asyncio
    async def test_needs_always_in_bounds(self, fake_bark_generator):
        """After any tick, all needs are within [0, 100]."""
        agent = create_dog_agent("Max", "Corgi", Personality.FOODIE)
        agent.bark_generator = fake_bark_generator

        for tick in range(100):
            await agent.process_tick(tick, park_state={})
            assert 0 <= agent.dog.needs.energy <= 100
            assert 0 <= agent.dog.needs.hunger <= 100
            assert 0 <= agent.dog.needs.boredom <= 100
```

#### 13.6.2 `test_orchestrator.py` — Full Tick Pipeline

```python
class TestOrchestrator:

    @pytest.mark.asyncio
    async def test_three_dogs_ten_ticks_consistent(self, fake_bark_generator):
        """3 dogs, 10 ticks. Shared state has correct dog count every tick."""
        orch = create_orchestrator(num_dogs=3, bark_generator=fake_bark_generator, seed=42)
        for tick in range(10):
            snapshot = await orch.run_tick()
            assert len(snapshot.dogs) == 3
            assert snapshot.tick == tick

    @pytest.mark.asyncio
    async def test_no_orphaned_play_pairs(self, fake_bark_generator):
        """After every tick, play pairs are symmetric: if A→B then B→A."""
        orch = create_orchestrator(num_dogs=6, bark_generator=fake_bark_generator, seed=42)
        for tick in range(50):
            snapshot = await orch.run_tick()
            playing = [d for d in snapshot.dogs if d.state == "playing"]
            for dog in playing:
                assert dog.play_partner is not None, f"{dog.name} playing but no partner at tick {tick}"
                partner = next((d for d in playing if d.name == dog.play_partner), None)
                assert partner is not None, f"{dog.name}'s partner {dog.play_partner} not found playing"
                assert partner.play_partner == dog.name, f"Asymmetric pair: {dog.name}↔{partner.name}"

    @pytest.mark.asyncio
    async def test_tick_events_emitted(self, fake_bark_generator):
        """State changes produce events in the tick snapshot."""
        orch = create_orchestrator(num_dogs=5, bark_generator=fake_bark_generator, seed=42)
        all_events = []
        for tick in range(30):
            snapshot = await orch.run_tick()
            all_events.extend(snapshot.events)
        # Over 30 ticks with 5 dogs, there must be some state changes
        assert len(all_events) > 0
        assert all(e.event_type in ("state_change", "play_start", "play_end") for e in all_events)
```

#### 13.6.3 `test_play_protocol.py` — Play Negotiation

```python
class TestPlayProtocol:

    @pytest.mark.asyncio
    async def test_two_dogs_pair_and_play(self, fake_bark_generator):
        """Force two dogs to want to play → they get paired."""
        buddy = make_dog("Buddy", state=SLEEPING, energy=95, hunger=20, boredom=70)
        luna = make_dog("Luna", state=SLEEPING, energy=95, hunger=20, boredom=70)
        orch = create_orchestrator_from_dogs([buddy, luna], bark_generator=fake_bark_generator)

        snapshot = await orch.run_tick()
        playing = [d for d in snapshot.dogs if d.state == "playing"]
        assert len(playing) == 2
        assert playing[0].play_partner == playing[1].name

    @pytest.mark.asyncio
    async def test_partner_exit_unpairs_both(self, fake_bark_generator):
        """When one dog leaves play (energy drops), both become unpaired."""
        buddy = make_dog("Buddy", state=PLAYING, energy=31, hunger=20, boredom=10, play_partner="Luna")
        luna = make_dog("Luna", state=PLAYING, energy=60, hunger=20, boredom=10, play_partner="Buddy")
        orch = create_orchestrator_from_dogs([buddy, luna], bark_generator=fake_bark_generator)

        snapshot = await orch.run_tick()
        # Buddy should exit play (energy will drop below 30 after -5 delta)
        buddy_snap = next(d for d in snapshot.dogs if d.name == "Buddy")
        luna_snap = next(d for d in snapshot.dogs if d.name == "Luna")
        assert buddy_snap.state != "playing"
        assert luna_snap.play_partner is None

    @pytest.mark.asyncio
    async def test_odd_dog_out_not_playing(self, fake_bark_generator):
        """3 dogs all want to play → 2 paired, 1 left out."""
        dogs = [
            make_dog(f"Dog{i}", state=SLEEPING, energy=95, hunger=20, boredom=70)
            for i in range(3)
        ]
        orch = create_orchestrator_from_dogs(dogs, bark_generator=fake_bark_generator)
        snapshot = await orch.run_tick()
        playing = [d for d in snapshot.dogs if d.state == "playing"]
        assert len(playing) == 2
```

#### 13.6.4 `test_api.py` — FastAPI Endpoint Tests

```python
class TestSimulationAPI:

    def test_start_simulation(self, client):
        resp = client.post("/api/simulation/start", json={"num_dogs": 5, "num_ticks": 50, "speed_ms": 0})
        assert resp.status_code == 200
        data = resp.json()
        assert "simulation_id" in data
        assert len(data["dogs"]) == 5

    def test_start_with_invalid_config(self, client):
        resp = client.post("/api/simulation/start", json={"num_dogs": 0, "num_ticks": 50})
        assert resp.status_code == 422

    def test_start_with_too_many_dogs(self, client):
        resp = client.post("/api/simulation/start", json={"num_dogs": 100, "num_ticks": 50})
        assert resp.status_code == 422

    def test_stop_running_simulation(self, client):
        client.post("/api/simulation/start", json={"num_dogs": 3, "num_ticks": 1000, "speed_ms": 100})
        resp = client.post("/api/simulation/stop")
        assert resp.status_code == 200
        assert resp.json()["status"] == "stopped"

    def test_stop_when_not_running(self, client):
        resp = client.post("/api/simulation/stop")
        assert resp.status_code == 409  # Conflict

    def test_status_when_idle(self, client):
        resp = client.get("/api/simulation/status")
        assert resp.status_code == 200
        assert resp.json()["running"] is False

    def test_status_when_running(self, client):
        client.post("/api/simulation/start", json={"num_dogs": 3, "num_ticks": 1000, "speed_ms": 100})
        resp = client.get("/api/simulation/status")
        data = resp.json()
        assert data["running"] is True
        assert len(data["dogs"]) == 3

    def test_start_while_already_running(self, client):
        client.post("/api/simulation/start", json={"num_dogs": 3, "num_ticks": 100, "speed_ms": 100})
        resp = client.post("/api/simulation/start", json={"num_dogs": 5, "num_ticks": 100})
        assert resp.status_code == 409  # Can't start two simulations
```

**Fixture for API tests:**

```python
@pytest.fixture
def client(fake_bark_generator):
    """FastAPI test client with Gemini mocked."""
    app.dependency_overrides[get_bark_generator] = lambda: fake_bark_generator
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()
```

---

### 13.7 End-to-End Tests

E2E tests validate the full system from the outside. They start the server, connect via HTTP/WebSocket, and assert on observable outcomes.

#### 13.7.1 `test_simulation.py` — Full Simulation Run

```python
class TestFullSimulation:

    @pytest.mark.asyncio
    async def test_sleep_ratio_within_target(self, running_server):
        """10 dogs, 200 ticks. Average sleep time is between 55-65%."""
        async with httpx.AsyncClient() as client:
            resp = await client.post(f"{BASE_URL}/api/simulation/start", json={
                "num_dogs": 10, "num_ticks": 200, "speed_ms": 0
            })
            sim_id = resp.json()["simulation_id"]
            await wait_for_completion(client, sim_id, timeout=60)

            stats = await client.get(f"{BASE_URL}/api/simulation/status")
            for dog in stats.json()["dogs"]:
                # Individual dogs should be in a reasonable range
                assert dog["sleep_pct"] >= 40, f"{dog['name']} only slept {dog['sleep_pct']}%"
                assert dog["sleep_pct"] <= 80, f"{dog['name']} slept {dog['sleep_pct']}% (too much)"

            # Average across all dogs should be near 60%
            avg_sleep = sum(d["sleep_pct"] for d in stats.json()["dogs"]) / 10
            assert 55 <= avg_sleep <= 65, f"Average sleep {avg_sleep}% outside target range"

    @pytest.mark.asyncio
    async def test_all_dogs_visit_all_states(self, running_server):
        """Every dog must spend >0% time in each of the three states."""
        async with httpx.AsyncClient() as client:
            await client.post(f"{BASE_URL}/api/simulation/start", json={
                "num_dogs": 5, "num_ticks": 200, "speed_ms": 0
            })
            await wait_for_completion(client, timeout=60)
            stats = await client.get(f"{BASE_URL}/api/simulation/status")
            for dog in stats.json()["dogs"]:
                assert dog["sleep_pct"] > 0, f"{dog['name']} never slept"
                assert dog["eat_pct"] > 0, f"{dog['name']} never ate"
                assert dog["play_pct"] > 0, f"{dog['name']} never played"

    @pytest.mark.asyncio
    async def test_json_log_valid(self, running_server, tmp_path):
        """JSON event log is parseable and has correct schema."""
        log_file = tmp_path / "events.json"
        async with httpx.AsyncClient() as client:
            await client.post(f"{BASE_URL}/api/simulation/start", json={
                "num_dogs": 3, "num_ticks": 50, "speed_ms": 0
            })
            await wait_for_completion(client, timeout=30)

        # Validate every line is valid JSON with expected fields
        with open(log_file) as f:
            for line in f:
                tick_data = json.loads(line)
                assert "tick" in tick_data
                assert "dogs" in tick_data
                assert "events" in tick_data
                for dog in tick_data["dogs"]:
                    assert dog["state"] in ("sleeping", "eating", "playing")
                    assert 0 <= dog["energy"] <= 100
                    assert 0 <= dog["hunger"] <= 100
                    assert 0 <= dog["boredom"] <= 100
                    assert isinstance(dog["bark"], str)
```

#### 13.7.2 `test_websocket.py` — Real-Time Streaming

```python
class TestWebSocketStream:

    @pytest.mark.asyncio
    async def test_receives_tick_events(self, running_server):
        """Connect to WS, start simulation, receive at least 5 tick events."""
        async with httpx.AsyncClient() as client:
            await client.post(f"{BASE_URL}/api/simulation/start", json={
                "num_dogs": 3, "num_ticks": 20, "speed_ms": 50
            })

        ticks_received = []
        async with websockets.connect(f"{WS_URL}/ws/stream") as ws:
            for _ in range(10):
                msg = await asyncio.wait_for(ws.recv(), timeout=5)
                data = json.loads(msg)
                ticks_received.append(data["tick"])

        assert len(ticks_received) >= 5
        assert ticks_received == sorted(ticks_received)  # ticks arrive in order

    @pytest.mark.asyncio
    async def test_ws_snapshot_schema(self, running_server):
        """Every WS message matches the TickSnapshot schema."""
        async with httpx.AsyncClient() as client:
            await client.post(f"{BASE_URL}/api/simulation/start", json={
                "num_dogs": 5, "num_ticks": 10, "speed_ms": 50
            })

        async with websockets.connect(f"{WS_URL}/ws/stream") as ws:
            msg = await asyncio.wait_for(ws.recv(), timeout=5)
            data = json.loads(msg)

            assert isinstance(data["tick"], int)
            assert isinstance(data["total_ticks"], int)
            assert isinstance(data["dogs"], list)
            assert len(data["dogs"]) == 5
            for dog in data["dogs"]:
                assert set(dog.keys()) >= {"name", "breed", "personality", "state",
                                           "energy", "hunger", "boredom", "bark", "play_partner"}

    @pytest.mark.asyncio
    async def test_ws_disconnects_cleanly_on_stop(self, running_server):
        """Stopping simulation sends a final message and closes WS."""
        async with httpx.AsyncClient() as client:
            await client.post(f"{BASE_URL}/api/simulation/start", json={
                "num_dogs": 3, "num_ticks": 1000, "speed_ms": 100
            })

        async with websockets.connect(f"{WS_URL}/ws/stream") as ws:
            await asyncio.wait_for(ws.recv(), timeout=5)  # at least one tick
            async with httpx.AsyncClient() as client:
                await client.post(f"{BASE_URL}/api/simulation/stop")
            # WS should close gracefully
            with pytest.raises(websockets.ConnectionClosed):
                await asyncio.wait_for(ws.recv(), timeout=5)
```

#### 13.7.3 `test_determinism.py` — Reproducibility

```python
class TestDeterminism:

    @pytest.mark.asyncio
    async def test_same_seed_same_fsm_transitions(self, running_server):
        """Two runs with identical seed produce identical state transition sequences."""
        transitions = []
        for run in range(2):
            async with httpx.AsyncClient() as client:
                await client.post(f"{BASE_URL}/api/simulation/start", json={
                    "num_dogs": 5, "num_ticks": 100, "speed_ms": 0, "seed": 42
                })
                await wait_for_completion(client, timeout=30)
                status = await client.get(f"{BASE_URL}/api/simulation/status")
                # Extract just the FSM transition sequence (not barks)
                run_transitions = [
                    (d["name"], d["state_history"])
                    for d in status.json()["dogs"]
                ]
                transitions.append(run_transitions)

        assert transitions[0] == transitions[1], "FSM transitions differ between identical-seed runs"

    @pytest.mark.asyncio
    async def test_different_seeds_different_outcomes(self):
        """Two different seeds produce different results (sanity check)."""
        results = []
        for seed in [42, 99]:
            async with httpx.AsyncClient() as client:
                await client.post(f"{BASE_URL}/api/simulation/start", json={
                    "num_dogs": 5, "num_ticks": 50, "speed_ms": 0, "seed": seed
                })
                await wait_for_completion(client, timeout=30)
                status = await client.get(f"{BASE_URL}/api/simulation/status")
                results.append(status.json())

        states_1 = [(d["name"], d["sleep_pct"]) for d in results[0]["dogs"]]
        states_2 = [(d["name"], d["sleep_pct"]) for d in results[1]["dogs"]]
        assert states_1 != states_2  # Different seeds should diverge
```

---

### 13.8 Performance & Stress Tests

Gated behind `--slow` flag. Not part of CI — run manually before releases or when tuning.

```python
@pytest.mark.slow
class TestPerformance:

    def test_10_dogs_1000_ticks_under_30s(self, fake_bark_generator):
        """FSM-only (no Gemini) completes 10 dogs × 1000 ticks in <30s."""
        import time
        orch = create_orchestrator(num_dogs=10, num_ticks=1000,
                                   bark_generator=fake_bark_generator, seed=42)
        start = time.monotonic()
        orch.run_all()
        elapsed = time.monotonic() - start
        assert elapsed < 30, f"Took {elapsed:.1f}s — expected <30s"

    def test_20_dogs_500_ticks_memory_stable(self, fake_bark_generator):
        """Memory usage stays flat — no leaks from event accumulation."""
        import tracemalloc
        tracemalloc.start()
        orch = create_orchestrator(num_dogs=20, num_ticks=500,
                                   bark_generator=fake_bark_generator, seed=42)
        orch.run_all()
        current, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        assert peak < 50 * 1024 * 1024  # Under 50MB peak

    def test_100_dogs_100_ticks_no_crash(self, fake_bark_generator):
        """Scale test: 100 dogs doesn't crash, completes, state is consistent."""
        orch = create_orchestrator(num_dogs=100, num_ticks=100,
                                   bark_generator=fake_bark_generator, seed=42)
        orch.run_all()
        snapshot = orch.get_final_snapshot()
        assert len(snapshot.dogs) == 100
        for dog in snapshot.dogs:
            assert dog.state in ("sleeping", "eating", "playing")
```

---

### 13.9 Test Helpers & Factories

Shared across all test layers to keep test code DRY and readable.

```python
# tests/factories.py

def make_dog(
    name: str = "TestDog",
    breed: str = "Mutt",
    personality: Personality = Personality.GRUMP,
    state: DogState = DogState.SLEEPING,
    energy: float = 50.0,
    hunger: float = 50.0,
    boredom: float = 50.0,
    play_partner: str | None = None,
) -> DogProfile:
    """Factory for DogProfile with sensible defaults and overridable fields."""
    return DogProfile(
        name=name,
        breed=breed,
        personality=personality,
        state=state,
        needs=DogNeeds(energy=energy, hunger=hunger, boredom=boredom),
        play_partner=play_partner,
        ticks_in_state=0,
        latest_bark="",
    )


async def wait_for_completion(client: httpx.AsyncClient, timeout: int = 30):
    """Poll /api/simulation/status until running=False or timeout."""
    import asyncio
    deadline = asyncio.get_event_loop().time() + timeout
    while asyncio.get_event_loop().time() < deadline:
        resp = await client.get(f"{BASE_URL}/api/simulation/status")
        if not resp.json()["running"]:
            return
        await asyncio.sleep(0.1)
    raise TimeoutError("Simulation did not complete within timeout")
```

---

### 13.10 CI Pipeline

```yaml
# .github/workflows/test.yml
name: Barkland Tests
on: [push, pull_request]

jobs:
  unit:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: "3.12" }
      - run: pip install -e ".[dev]"
      - run: pytest tests/unit/ -v --cov=barkland/engine --cov-fail-under=90

  integration:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: "3.12" }
      - run: pip install -e ".[dev]"
      - run: pytest tests/integration/ -v --cov=barkland --cov-fail-under=75

  e2e:
    runs-on: ubuntu-latest
    needs: [unit, integration]
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: "3.12" }
      - run: pip install -e ".[dev]"
      - run: pytest tests/e2e/ -v --timeout=120
      # Note: e2e runs WITHOUT --live-llm in CI (uses FakeBarkGenerator)
      # Live Gemini tests are run manually before releases

  lint:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: "3.12" }
      - run: pip install ruff mypy
      - run: ruff check barkland/ tests/
      - run: mypy barkland/ --strict
```

---

### 13.11 Test Coverage Requirements

| Package | Min Coverage | Rationale |
|---|---|---|
| `barkland/engine/` (fsm, needs, matching) | **90%** | Core simulation logic — must be airtight |
| `barkland/agents/` | **80%** | Agent wiring — tested with mocked Gemini |
| `barkland/models/` | **85%** | Data classes — validation and serialization |
| `barkland/api/` | **80%** | REST/WS endpoints — tested via httpx TestClient |
| `barkland/output/` | **70%** | Logging/stats — lower risk, tested indirectly by e2e |
| **Overall** | **80%** | Enforced in CI via `--cov-fail-under` |

### 13.12 Testing Principles Checklist

Before any PR is merged, verify:

- [ ] All FSM transition boundary values tested (==, ==±1 for every threshold)
- [ ] Every new state gets at least 5 unit tests covering entry, exit, and edge cases
- [ ] Play matching tested with 0, 1, 2, 3, even, odd, and max dog counts
- [ ] Integration tests use `FakeBarkGenerator`, never real Gemini
- [ ] E2E tests pass with `speed_ms=0` (no artificial delays in CI)
- [ ] No test depends on execution order (`pytest-randomly` compatible)
- [ ] No test uses `time.sleep` (use `asyncio.wait_for` with timeout instead)
- [ ] Flaky test = bug. Investigate and fix, never mark as `xfail`
- [ ] New API endpoints get both happy-path and error-path test cases
- [ ] WebSocket tests assert on both message schema and delivery order

---

## 14. Consistency & Performance

### 14.1 Determinism

- FSM transitions use a seeded `random.Random(seed)` — fully reproducible
- Bark translations are **not** deterministic (LLM output varies) — this is expected and fine
- `test_determinism.py` validates FSM-level determinism only

### 14.2 Race Condition Prevention

- 3-phase tick architecture: Decide → Resolve → Execute
- All shared state mutations happen in the single-threaded resolver (Phase 2)
- WebSocket broadcasts happen after the tick is fully committed

### 14.3 Gemini Flash Latency

- Gemini 2.0 Flash p50 latency: ~200-400ms for short responses
- With N dogs in parallel (Phase 3): all bark calls fire concurrently
- Expected tick time: ~500ms (FSM) + ~400ms (parallel Gemini calls) ≈ ~1s total
- The `speed_ms` UI slider adds artificial delay on top of actual tick time

### 14.4 Memory

- Each dog: ~500 bytes state + ~200 bytes latest bark
- 20 dogs × 500 ticks: ~60KB live state, ~2MB JSON event log
- No memory concerns for V1 scale

---

## 15. Dog Name & Breed Pool

### 15.1 Names (Randomly Assigned)

```python
DOG_NAMES = [
    "Buddy", "Luna", "Max", "Daisy", "Rocky",
    "Bella", "Charlie", "Coco", "Duke", "Penny",
    "Bear", "Sadie", "Milo", "Rosie", "Tucker",
    "Lola", "Zeus", "Nala", "Biscuit", "Pepper",
]
```

### 15.2 Breeds (Cosmetic — Affects Personality Prompts)

```python
DOG_BREEDS = [
    "Golden Retriever", "Husky", "French Bulldog", "Corgi",
    "German Shepherd", "Poodle", "Beagle", "Labrador",
    "Shiba Inu", "Dachshund", "Border Collie", "Pug",
    "Dalmatian", "Chihuahua", "Great Dane", "Bulldog",
]
```

---

## 16. Implementation Plan

| Phase | Tasks | Est. Time |
|---|---|---|
| **Phase 1: Core Engine** | Models, FSM, needs, matching — unit tests for all | 2 days |
| **Phase 2: ADK + Gemini** | DogAgent with LlmAgent, orchestrator, personality system, bark generation | 3 days |
| **Phase 3: API Layer** | FastAPI routes, WebSocket streaming, simulation lifecycle | 2 days |
| **Phase 4: Web UI** | React app, dog cards, need bars, event log, controls | 3 days |
| **Phase 5: Containerize** | Dockerfile, sandbox manifests, GKE deployment, warm pool | 2 days |
| **Phase 6: Integration + E2E** | Multi-dog tests, WebSocket tests, sleep ratio validation | 2 days |
| **Phase 7: Polish** | README, demo script, JSON log viewer, final tuning | 1 day |

**Total estimate: 15 days**

---


*This document is ready for design review. All sections open for discussion before implementation begins.*
