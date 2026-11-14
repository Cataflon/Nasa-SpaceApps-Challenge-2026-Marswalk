# Marswalk Copilot: pitch (3 minutes)

### 0:00 · The problem

Twenty-seven minutes. That's how long an astronaut on Mars would wait for help from Earth. In an environment with dust devils, storm fronts, solar storms and possible air leaks, conditions change in seconds, thats plenty of time for Marswalk.

### 0:22 · What we built

For this Interplanetary Survival Guide, we built a 10 by 10 km map of the Jezero crater from NASA sources, checked against 306 positions of the Perseverance rover, and a live copilot that follows the walk continously.

### 0:37 · Every hazard, in real time

Before the walk, the route avoids steep slopes, cliffs and soft sand, within the limits of oxygen, daylight and radiation.
During the walk, it watches out for several kinds of dangers.
For a moving hazard, using sattelite data and specific sensors, it predicts where it will be, not just where it is now, and redraws the route around it before it arrives.
If there is no safe way around, it waits for the hazard to pass, takes shelter, or heads home, whichever is safest.

### 1:10 · The rule we never broke

We do not put an astronaut's life in the hands of an AI.
Every decision is deterministic: the same situation always gives the same decision.
The code computes the oxygen, the time, the radiation dose and the risk of many other factors.
A validator removes every option that is not safe, and a fixed rule picks the safest one left.
The language model only explains the decision. The decision does not change.

### 1:42 · Video (talk over it)

adauga tu serban si vorbeste si despre telefon si ceas fara sa repeti ce e deja spus daca poti

### 2:12 · The result

We ran 100 simulated storms, the same for both.
Following the plan, the astronaut came home safely 51 times. With the copilot: 81 times.
It never turned a safe walk into an unsafe one.


### 2:33 · A simulator and a copilot

It works the way aviation software does.
It can be used as a simulator, like the ones pilots train on, crews rehearse walks and storms on real Jezero terrain before leaving Earth.
As a copilot in the suit, like the cockpit system that tells pilots to climb or descend, it gives one clear, deterministic instruction, with its reason.
And for every walk, it prints a one-page Survival Guide.

### 2:59 · Closing

On Earth, the same engine can guide mountain rescue teams.
Marswalk Copilot: the code decides, the astronaut comes home. Thank you.

