"""16 scenario cases, one per behaviour group.

Written fresh, not copied from the dataset or from earlier tests. Each case
states what SHOULD happen, so the same list works three ways:

    python scripts/run_scenarios.py        # prints a pass/fail table
    make test                              # runs them as pytest cases
    TEST_CASES.md                          # manual script for the demo
"""

SCENARIOS = [
    {"id": 1, "group": "Electrical danger",
     "text": "the switch in the hallway is buzzing and smells like burning plastic",
     "community": "Darwin (Nightcliff)",
     "expect": {"tier": "Immediate", "advice": "meter box"}},

    {"id": 2, "group": "Gas leak",
     "text": "i can smell gas near the heater, the kids are asleep inside",
     "community": "Katherine", "vulnerability": ["children"],
     "expect": {"tier": "Immediate", "whole_dwelling": True, "advice": "gas off at the bottle"}},

    {"id": 3, "group": "Storm or cyclone damage",
     "text": "after the storm last night half the roof is missing and water is pouring into the kids room",
     "community": "Wadeye",
     "expect": {"tier": "Immediate", "whole_dwelling": True}},

    {"id": 4, "group": "Sewage inside",
     "text": "the toilet overflowed and sewage is all over the bathroom floor",
     "community": "Maningrida",
     "expect": {"tier": "Immediate"}},

    {"id": 5, "group": "House cannot be secured",
     "text": "someone broke our back door and it wont close or lock now",
     "community": "Darwin (Casuarina)",
     "expect": {"tier": "Immediate", "whole_dwelling": False}},

    {"id": 6, "group": "Essential service lost",
     "text": "no hot water since friday, we have been having cold showers with a baby",
     "community": "Howard Springs", "vulnerability": ["children"],
     "expect": {"tier": "Urgent"}},

    {"id": 7, "group": "Clarifying question",
     "text": "the toilet wont flush",
     "community": "Galiwinku",
     "expect": {"asks": "only toilet", "answer": "yes only one", "tier_after": "Urgent"}},

    {"id": 8, "group": "Routine repair",
     "text": "the flyscreen on the bedroom window has a big hole in it",
     "community": "Darwin (Parap)",
     "expect": {"tier": "Routine"}},

    {"id": 9, "group": "Second-language English",
     "text": "fridge power socket make smoke yesterday, we scared to use",
     "community": "Numbulwar",
     "expect": {"tier": "Immediate"}},

    {"id": 10, "group": "Hedged hazard",
     "text": "might be nothing but there is a funny smell like gas in the laundry",
     "community": "Palmerston (Gray)",
     "expect": {"tier": "Immediate"}},

    {"id": 11, "group": "Hazard buried in small talk",
     "text": "hi just wanted to say thanks for fixing the gate. also water is dripping onto the light switch in the bathroom",
     "community": "Belyuen",
     "expect": {"tier": "Immediate"}},

    {"id": 12, "group": "Too vague to rank",
     "text": "something is not right with the shower, not sure what it is",
     "community": "Darwin (Karama)",
     "expect": {"asks": "what is wrong"}},

    {"id": 13, "group": "Problem already fixed",
     "text": "the leak you fixed last week is all good now, no water coming in",
     "community": "Darwin (Malak)",
     "expect": {"tier": "NotInQueue", "status": "not_in_queue"}},

    {"id": 14, "group": "Withdrawal",
     "text": "dont worry about the fan anymore, we will manage",
     "community": "Gunbalanya",
     "expect": {"tier": "NotInQueue", "status": "awaiting_confirmation",
                "says": "We have not closed your repair"}},

    {"id": 15, "group": "Tenant already made it safe",
     "text": "the powerpoint started sparking so i turned the power off at the switchboard",
     "community": "Palmerston (Driver)",
     "expect": {"tier": "Immediate", "tenant_isolated": True,
                "says": "Thank you for making it safe"}},

    {"id": 16, "group": "Emergency, revealed in an answer",
     "text": "not sure what it is",
     "community": "Darwin (Parap)",
     "expect": {"asks": "what is wrong", "answer": "perhaps the gas is on fire",
                "tier_after": "Immediate", "says": "call 000 now"}},
]
