# 🤖 Daily AI/Robotics Paper Briefing

VLA, World Model, Physical AI 관련 논문을 매일 자동으로 검색하고 한국어로 요약합니다.

## 📅 주요 검색 키워드
- Vision-Language-Action (VLA)
- World Model for Robotics
- Physical AI / Embodied AI

## 🏢 주요 추적 기관/저자
- **기관**: Gemini Robotics, Physical Intelligence, NVIDIA
- **저자**: Yann LeCun, Chelsea Finn, Sergey Levine, Moo Jin Kim, Seonghyeon Ye

## 📊 최근 논문 (카테고리별)

### VLA

| 날짜 | 제목 | 저자 | 링크 |
|------|------|------|------|
| 2026-03-21 | From Inference Efficiency to Embodied Efficiency: Revisiting Efficiency Metrics for Vision-Language-Action Models | Zhuofan Li, Hongkun Yang, Zhenyang Chen | [arXiv](https://arxiv.org/abs/2603.19131) |
| 2026-03-21 | Not All Features Are Created Equal: A Mechanistic Study of Vision-Language-Action Models | Bryce Grant, Xijia Zhao, Peng Wang | [arXiv](https://arxiv.org/abs/2603.19233) |
| 2026-03-20 | ForceVLA2: Unleashing Hybrid Force-Position Control with Force Awareness for Contact-Rich Manipulation | Yang Li,  Zhaxizhuoma, Hongru Jiang | [arXiv](https://arxiv.org/abs/2603.15169) |
| 2026-03-20 | ProbeFlow: Training-Free Adaptive Flow Matching for Vision-Language-Action Models | Zhou Fang, Jiaqi Wang, Yi Zhou | [arXiv](https://arxiv.org/abs/2603.17850) |
| 2026-03-20 | HeiSD: Hybrid Speculative Decoding for Embodied Vision-Language-Action Models with Kinematic Awareness | Zihao Zheng, Zhihao Mao, Sicheng Tian | [arXiv](https://arxiv.org/abs/2603.17573) |
| 2026-03-20 | KineVLA: Towards Kinematics-Aware Vision-Language-Action Models with Bi-Level Action Decomposition | Gaoge Han, Zhengqing Gao, Ziwen Li | [arXiv](https://arxiv.org/abs/2603.17524) |

### World Model

| 날짜 | 제목 | 저자 | 링크 |
|------|------|------|------|
| 2026-03-21 | OmniVTA: Visuo-Tactile World Modeling for Contact-Rich Robotic Manipulation | Yuhang Zheng, Songen Gu, Weize Li | [arXiv](https://arxiv.org/abs/2603.19201) |
| 2026-03-20 | Kinema4D: Kinematic 4D World Modeling for Spatiotemporal Embodied Simulation | Mutian Xu, Tianbao Zhang, Tianqi Liu | [arXiv](https://arxiv.org/abs/2603.16669) |
| 2026-03-19 | V-JEPA 2.1: Unlocking Dense Features in Video Self-Supervised Learning | Lorenzo Mur-Labadia, Matthew Muckley, Amir Bar | [arXiv](https://arxiv.org/abs/2603.14482) |
| 2026-03-19 | Representation Learning for Spatiotemporal Physical Systems | Helen Qu, Rudy Morel, Michael McCabe | [arXiv](https://arxiv.org/abs/2603.13227) |
| 2026-03-19 | Temporal Straightening for Latent Planning | Ying Wang, Oumayma Bounou, Gaoyue Zhou | [arXiv](https://arxiv.org/abs/2603.12231) |

### Physical AI

| 날짜 | 제목 | 저자 | 링크 |
|------|------|------|------|
| 2026-03-23 | The Era of End-to-End Autonomy: Transitioning from Rule-Based Driving to Large Driving Models | Eduardo Nebot, Julie Stephany Berrio Perez | [arXiv](https://arxiv.org/abs/2603.16050) |

### Other

| 날짜 | 제목 | 저자 | 링크 |
|------|------|------|------|
| 2026-03-21 | MERGE: Guided Vision-Language Models for Multi-Actor Event Reasoning and Grounding in Human-Robot Interaction | Joerg Deigmoeller, Nakul Agarwal, Stephan Hasler | [arXiv](https://arxiv.org/abs/2603.18988) |
| 2026-03-21 | NavTrust: Benchmarking Trustworthiness for Embodied Navigation | Huaide Jiang, Yash Chaudhary, Yuping Wang | [arXiv](https://arxiv.org/abs/2603.19229) |
| 2026-03-19 | Why AI systems don't learn and what to do about it: Lessons on autonomous learning from cognitive science | Emmanuel Dupoux, Yann LeCun, Jitendra Malik | [arXiv](https://arxiv.org/abs/2603.15381) |
| 2026-03-19 | The Spike, the Sparse and the Sink: Anatomy of Massive Activations and Attention Sinks | Shangwen Sun, Alfredo Canziani, Yann LeCun | [arXiv](https://arxiv.org/abs/2603.05498) |

## 🦾 VLA 스터디 논문 목록

> [awesome-vla-study](https://github.com/MilkClouds/awesome-vla-study) 기반 커리큘럼

### Phase 2: Early Foundation RFMs & Robot Policy

| # | 논문 | 링크 | 주제 |
|---|------|------|------|
| 1 | RT-1: Robotics Transformer — Brohan et al. (2022) | [2212.06817](https://arxiv.org/abs/2212.06817) | First large-scale Robotics Transformer |
| 2 | RT-2: Vision-Language-Action Models — Brohan et al. (2023) | [2307.15818](https://arxiv.org/abs/2307.15818) | VLM backbone → VLA paradigm |
| 3 | Octo — Ghosh et al. (2024) | [2405.12213](https://arxiv.org/abs/2405.12213) | Open-source generalist policy, OXE pretrained |
| 4 | OpenVLA — Kim et al. (2024) | [2406.09246](https://arxiv.org/abs/2406.09246) | First open-source VLM-based VLA |
| 5 | BeT — Shafiullah et al. (2022) | [2206.11251](https://arxiv.org/abs/2206.11251) | Multimodal action discretization |
| 6 | Diffusion Policy — Chi et al. (2023) | [2303.04137](https://arxiv.org/abs/2303.04137) | Diffusion for robot control |
| 7 | ACT/ALOHA — Zhao et al. (2023) | [2304.13705](https://arxiv.org/abs/2304.13705) | Action Chunking Transformer, bimanual |

### Phase 3: Current RFM Architectures

| # | 논문 | 링크 | 주제 |
|---|------|------|------|
| 8 | CogACT — Li et al. (2024) | [2411.19650](https://arxiv.org/abs/2411.19650) | VLM + DiT action head |
| 9 | GR00T N1 — Bjorck et al. (2025) | [2503.14734](https://arxiv.org/abs/2503.14734) | 2B diffusion transformer, humanoid |
| 10 | X-VLA — Zheng et al. (2025) | [2510.10274](https://arxiv.org/abs/2510.10274) | Cross-embodiment, flow matching |
| 11 | π0 — Black et al. (2024) | [2410.24164](https://arxiv.org/abs/2410.24164) | Flow matching + action expert |
| 12 | InternVLA-M1 — Chen et al. (2025) | [2510.13778](https://arxiv.org/abs/2510.13778) | Spatial grounding → action generation |

### Phase 4: Data Scaling

| # | 논문 | 링크 | 주제 |
|---|------|------|------|
| 13 | Open X-Embodiment (OXE) — (2023) | [2310.08864](https://arxiv.org/abs/2310.08864) | 1M+ trajectories, 22 embodiments |
| 14 | AgiBot World — Bu et al. (2025) | [2503.06669](https://arxiv.org/abs/2503.06669) | 1M+ trajectories, 217 tasks |
| 15 | UMI — Chi et al. (2024) | [2402.10329](https://arxiv.org/abs/2402.10329) | Robot-free SE(3) data collection |
| 16 | VITRA — Li et al. (2025) | [2510.21571](https://arxiv.org/abs/2510.21571) | Human video → VLA training data |
| 17 | Human to Robot Transfer — Kareer et al. (2025) | [2512.22414](https://arxiv.org/abs/2512.22414) | Human video → robot transfer |

### Phase 5: Efficient Inference & Dual-System

| # | 논문 | 링크 | 주제 |
|---|------|------|------|
| 18 | SmolVLA — Shukor et al. (2025) | [2506.01844](https://arxiv.org/abs/2506.01844) | 450M params, model compression |
| 19 | RTC — Black et al. (2025) | [2506.07339](https://arxiv.org/abs/2506.07339) | Async inference, freezing + inpainting |
| 20 | Helix — Figure AI (2025) | [figure.ai/news/helix](https://www.figure.ai/news/helix) | Dual-system humanoid |
| 21 | Fast-in-Slow — Chen et al. (2025) | [2506.01953](https://arxiv.org/abs/2506.01953) | End-to-end trainable dual-system |

### Phase 6: RL Fine-tuning, Reasoning & World Model

| # | 논문 | 링크 | 주제 |
|---|------|------|------|
| 22 | HIL-SERL — Luo et al. (2024) | [2410.21845](https://arxiv.org/abs/2410.21845) | Human-in-the-loop RL |
| 23 | SimpleVLA-RL — Li et al. (2025) | [2509.09674](https://arxiv.org/abs/2509.09674) | RL fine-tuning for AR VLA |
| 24 | π*0.6 / Recap — PI (2025) | [2511.14759](https://arxiv.org/abs/2511.14759) | RL for flow-based VLA |
| 25 | CoT-VLA — Zhao et al. (2025) | [2503.22020](https://arxiv.org/abs/2503.22020) | Visual chain-of-thought reasoning |
| 26 | ThinkAct — Huang et al. (2025) | [2507.16815](https://arxiv.org/abs/2507.16815) | Decouple reasoning from execution |
| 27 | Fast-ThinkAct — Huang et al. (2026) | [2601.09708](https://arxiv.org/abs/2601.09708) | Latent distillation, ~10x speed |
| 28 | UniVLA — Wang et al. (2025) | [2506.19850](https://arxiv.org/abs/2506.19850) | Unified AR VLA with world modeling |
| 29 | Cosmos Policy — Kim et al. (2026) | [2601.16163](https://arxiv.org/abs/2601.16163) | Video FM as robot policy backbone |
| 30 | DreamZero — Ye et al. (2026) | [dreamzero0.github.io](https://dreamzero0.github.io/) | Joint world+action generation |

## 📚 브리핑 아카이브

- [2026-03-23](./2026/03/2026-03-23.md)
- [2026-03-22](./2026/03/2026-03-22.md)
- [2026-03-21](./2026/03/2026-03-21.md)
- [2026-03-20](./2026/03/2026-03-20.md)
- [2026-03-19](./2026/03/2026-03-19.md)
