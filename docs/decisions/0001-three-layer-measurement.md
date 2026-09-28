# ADR-0001: Real GPU, calibrated simulator and emulated AWS as separate layers

- **Status:** Accepted
- **Date:** 2026-09-27

## Context

Relay has 2M users. Reproducing that load on real GPUs would take a fleet of them, which is far beyond this project's budget. But inference performance claims are only credible if they trace back to real hardware, and quality claims require the real model.

## Options considered

1. **Real GPUs only.** Most credible per number, but limited to single-GPU scale. Autoscaling, cold starts and launch-scale capacity can't be shown.
2. **Simulation only.** Cheap and scales to any traffic, but uncalibrated numbers are guesses, and quality can't be measured at all.
3. **Layered:** real GPU for ground truth and quality, a simulator calibrated against it for scale, and an AWS emulator for customer-side plumbing.

## Decision

Option 3. Every result is tagged with the layer it came from (`gpu`, `sim`, `projection`, `floci`). See [methodology](../methodology.md).

## Consequences

- The whole stack can be developed at zero cost against the simulator before renting GPUs.
- Launch-scale numbers are projections and must be labelled as such everywhere.
- The simulator's calibration error has to be measured and reported. If it's large, conclusions at scale weaken.
- Floci can't exercise autoscaling (its Application Auto Scaling policies are stored but inert), so autoscaling behavior is modelled in our own code against the simulator.
