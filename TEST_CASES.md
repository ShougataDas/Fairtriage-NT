# FairTriage NT: 16 test cases

One case per behaviour group, written fresh rather than copied from the
dataset. Type each into the tenant form at `/tenant`, or run them all at once:

```bash
python scripts/run_scenarios.py             # pass/fail table
python scripts/run_scenarios.py --show 16   # full tenant text for one case
```

Every case should also say the same rank would apply in Darwin. That is the
location-fairness check, and the runner fails any case where it does not.

| # | Group | Community | Message | Should happen | Result |
|---|---|---|---|---|---|
| 1 | Electrical danger | Darwin (Nightcliff) | the switch in the hallway is buzzing and smells like burning plastic | Immediate; make-safe advice | Pass: Immediate |
| 2 | Gas leak | Katherine | i can smell gas near the heater, the kids are asleep inside | Immediate; whole house; make-safe advice | Pass: Immediate |
| 3 | Storm or cyclone damage | Wadeye | after the storm last night half the roof is missing and water is pouring into the kids room | Immediate; whole house | Pass: Immediate |
| 4 | Sewage inside | Maningrida | the toilet overflowed and sewage is all over the bathroom floor | Immediate | Pass: Immediate |
| 5 | House cannot be secured | Darwin (Casuarina) | someone broke our back door and it wont close or lock now | Immediate | Pass: Immediate |
| 6 | Essential service lost | Howard Springs | no hot water since friday, we have been having cold showers with a baby | Urgent | Pass: Urgent |
| 7 | Clarifying question | Galiwinku | the toilet wont flush | asks a question (only toilet); after answering "yes only one": Urgent | Pass: Urgent |
| 8 | Routine repair | Darwin (Parap) | the flyscreen on the bedroom window has a big hole in it | Routine | Pass: Routine |
| 9 | Second-language English | Numbulwar | fridge power socket make smoke yesterday, we scared to use | Immediate | Pass: Immediate |
| 10 | Hedged hazard | Palmerston (Gray) | might be nothing but there is a funny smell like gas in the laundry | Immediate | Pass: Immediate |
| 11 | Hazard buried in small talk | Belyuen | hi just wanted to say thanks for fixing the gate. also water is dripping onto the light switch in the bathroom | Immediate | Pass: Immediate |
| 12 | Too vague to rank | Darwin (Karama) | something is not right with the shower, not sure what it is | asks a question (what is wrong) | Pass: asked a question |
| 13 | Problem already fixed | Darwin (Malak) | the leak you fixed last week is all good now, no water coming in | not queued | Pass: NotInQueue |
| 14 | Withdrawal | Gunbalanya | dont worry about the fan anymore, we will manage | not queued; not auto-closed | Pass: NotInQueue |
| 15 | Tenant already made it safe | Palmerston (Driver) | the powerpoint started sparking so i turned the power off at the switchboard | Immediate; credited as made safe | Pass: Immediate |
| 16 | Emergency, revealed in an answer | Darwin (Parap) | not sure what it is | asks a question (what is wrong); after answering "perhaps the gas is on fire": Immediate; told to call 000 first | Pass: Immediate |

## Things to watch for when you run them by hand

- **Case 7** stops and asks *Is this the only toilet in the house?* Answer
  "yes only one" and it becomes Urgent. Answer "no there is another" and it
  becomes Routine. Same message, different tier, because the situation differs.
- **Case 9** is second-language English with the device named first
  ("socket make smoke"). It failed on the first run and was fixed. The fix
  briefly broke 80 negated reports and was caught by the evaluation.
- **Case 10** hedges ("might be nothing but... like gas"). A hedged hazard
  must still be treated as a hazard.
- **Case 12** is too vague to rank, so it asks instead of guessing.
- **Case 14** must not be closed. After a long wait, "don't worry about it"
  can mean fixed or can mean given up.
- **Case 15** is Immediate but ranks below live hazards, because the tenant
  says they switched the power off. The tenant is thanked instead of told how.
- **Case 16** is a real failure from testing. The tenant's first message is
  vague, and their answer to our question is "perhaps the gas is on fire". The
  system used to reply that it could not tell what needed fixing and drop the
  report out of the queue. It must now tell them to call 000 before anything
  else, show their answer back to them, and put the job at the top.
- **Cases 3 and 9** are remote. Compare their wait with the Darwin cases: the
  rank rule is the same, the wait is not, and the docket says why.

Results above come from the keyword rules. Re-run with the model switched on
(`FAIRTRIAGE_EXTRACTOR=openai`) to compare.