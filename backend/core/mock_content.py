"""Canned story CHAPTERS used when USE_MOCK_LLM=true (and as the ultimate safety
net if the real LLM keeps returning unparseable output).

Keyed by topic title. Each chapter matches the dict shape that
core.llm.generate_chapter returns: setting, title, paragraphs (list), summary,
and questions (each with a `concept` label). Content is realistic (Sri Lankan
settings, Grade 6-9 level) so it screenshots well.
"""

import copy

MOCK_CHAPTERS = {
    "Water Cycle": {
        "setting": "Amaya and her science teacher, in the hills around Kandy.",
        "title": "The Journey of a Raindrop",
        "paragraphs": [
            "Amaya watched the morning mist rise from the paddy fields near her home in Kandy. "
            "'Where does all that water go?' she wondered. Her teacher smiled and explained the "
            "water cycle — the never-ending journey water takes around our planet.",
            "When the sun heats rivers, lakes and the ocean, liquid water turns into an invisible "
            "gas called water vapour. This is evaporation. The warm vapour rises and cools high in "
            "the sky, turning back into tiny droplets that form clouds — a step called condensation.",
            "When the droplets grow heavy, they fall as rain, or precipitation. The rain flows into "
            "streams and rivers and back to the sea, and the whole journey begins again. The same "
            "water has been travelling this loop for millions of years!",
        ],
        "summary": "Amaya learned the water cycle: evaporation, condensation and precipitation move "
                   "water around the Earth in an endless loop.",
        "questions": [
            {
                "question": "What is the process called when liquid water turns into water vapour?",
                "options": ["Condensation", "Evaporation", "Precipitation", "Collection"],
                "correct_index": 1,
                "hint": "Think about what the sun's heat does to a puddle on a hot day.",
                "concept": "evaporation",
            },
            {
                "question": "What happens to water vapour when it cools high in the sky?",
                "options": ["It disappears", "It condenses into droplets", "It freezes into rock", "It becomes oxygen"],
                "correct_index": 1,
                "hint": "It is the step that forms clouds.",
                "concept": "condensation",
            },
        ],
    },
    "Photosynthesis": {
        "setting": "Nuwan and his older sister, in their garden in Galle.",
        "title": "The Green Food Factory",
        "paragraphs": [
            "In his garden in Galle, Nuwan noticed that the plants near the window grew taller than "
            "the ones in the shade. His sister explained that plants make their own food using "
            "sunlight, in a process called photosynthesis.",
            "Inside their green leaves is a substance called chlorophyll, which captures energy from "
            "sunlight. The leaves take in carbon dioxide from the air, and the roots draw up water "
            "from the soil.",
            "Using the sun's energy, the plant combines carbon dioxide and water to make glucose — a "
            "sugar it uses as food — and releases oxygen into the air. That oxygen is the very gas we "
            "breathe.",
        ],
        "summary": "Nuwan learned that plants use chlorophyll, sunlight, water and carbon dioxide to "
                   "make glucose, releasing oxygen.",
        "questions": [
            {
                "question": "Which gas do plants take in from the air for photosynthesis?",
                "options": ["Oxygen", "Nitrogen", "Carbon dioxide", "Hydrogen"],
                "correct_index": 2,
                "hint": "It is the same gas that humans breathe out.",
                "concept": "carbon dioxide",
            },
            {
                "question": "What does a plant release that animals need in order to breathe?",
                "options": ["Carbon dioxide", "Glucose", "Oxygen", "Chlorophyll"],
                "correct_index": 2,
                "hint": "It is the gas given off as a by-product of making food.",
                "concept": "oxygen",
            },
        ],
    },
    "States of Matter": {
        "setting": "Tharini and her father, on a hot afternoon in Jaffna.",
        "title": "The Melting Ice Cube",
        "paragraphs": [
            "On a hot day in Jaffna, Tharini took an ice cube from the freezer and watched it slowly "
            "turn into a puddle. Her father used it to explain the three states of matter.",
            "Solids, like the ice cube, have a fixed shape because their particles are packed tightly "
            "and can only vibrate in place. Liquids, like the puddle, take the shape of their "
            "container because their particles can slide past one another.",
            "Gases, like the steam from a boiling pot, spread out to fill any space because their "
            "particles move freely. Adding heat gives particles more energy, so a solid can melt into "
            "a liquid, and a liquid can boil into a gas.",
        ],
        "summary": "Tharini learned how solids, liquids and gases differ in how their particles are "
                   "arranged, and how heat changes one state into another.",
        "questions": [
            {
                "question": "Why does a liquid take the shape of its container?",
                "options": [
                    "Its particles are locked in place",
                    "Its particles can slide past each other",
                    "It has no particles",
                    "Its particles escape into the air",
                ],
                "correct_index": 1,
                "hint": "Compare how tightly particles are held in a solid versus a liquid.",
                "concept": "liquids",
            },
            {
                "question": "What happens to the particles when you add heat to a solid?",
                "options": ["They gain energy and move more", "They lose energy", "They vanish", "They get heavier"],
                "correct_index": 0,
                "hint": "Heat is a form of energy.",
                "concept": "changes of state",
            },
        ],
    },
    "Ecosystems & Food Chains": {
        "setting": "Kavindu and a forest guide, on a school trip near Sigiriya.",
        "title": "The Forest's Hidden Links",
        "paragraphs": [
            "During a school trip to a forest near Sigiriya, Kavindu learned how living things depend "
            "on one another. His guide described a food chain: grass grows using sunlight, a "
            "grasshopper eats the grass, a frog eats the grasshopper, and a snake eats the frog.",
            "Energy passes along the chain from one living thing to the next. The grass is a producer "
            "because it makes its own food. The animals are consumers because they eat other living "
            "things.",
            "When plants and animals die, decomposers like fungi and bacteria break them down, "
            "returning nutrients to the soil. This keeps the whole ecosystem in balance.",
        ],
        "summary": "Kavindu learned how energy flows from producers to consumers, and how decomposers "
                   "recycle nutrients to keep an ecosystem balanced.",
        "questions": [
            {
                "question": "In a food chain, what do we call a plant that makes its own food?",
                "options": ["Consumer", "Producer", "Predator", "Decomposer"],
                "correct_index": 1,
                "hint": "It 'produces' its own food from sunlight.",
                "concept": "producers",
            },
            {
                "question": "What is the main job of decomposers such as fungi and bacteria?",
                "options": [
                    "To make food from sunlight",
                    "To hunt large animals",
                    "To break down dead things and return nutrients to the soil",
                    "To produce oxygen",
                ],
                "correct_index": 2,
                "hint": "Think about what happens to a fallen leaf over time.",
                "concept": "decomposers",
            },
        ],
    },
    "Energy & Electricity": {
        "setting": "Senuri and her older brother, at home in Colombo after a power cut.",
        "title": "After the Power Cut",
        "paragraphs": [
            "When the lights came back after a power cut, Senuri asked her brother how electricity "
            "reaches their home in Colombo. He explained that electricity is a flow of tiny charged "
            "particles that needs a complete loop called a circuit.",
            "In a simple circuit, a battery pushes the charge around wires to a bulb and back again. "
            "If there is a gap — like an open switch — the flow stops and the bulb goes dark.",
            "He also explained that energy cannot be created or destroyed, only changed from one form "
            "to another. In a bulb, electrical energy becomes light and heat; in a fan, it becomes "
            "movement.",
        ],
        "summary": "Senuri learned that electricity needs a complete circuit, and that energy is never "
                   "destroyed but changes from one form to another.",
        "questions": [
            {
                "question": "What must a simple circuit have for electricity to flow and light a bulb?",
                "options": ["A gap in the wire", "A complete, unbroken loop", "Only a bulb", "An open switch"],
                "correct_index": 1,
                "hint": "Think about what happens when you open a switch.",
                "concept": "circuits",
            },
            {
                "question": "What happens to electrical energy inside a light bulb?",
                "options": ["It is destroyed", "It changes into light and heat", "It is created from nothing", "It disappears"],
                "correct_index": 1,
                "hint": "Energy is never used up; it only transforms.",
                "concept": "energy transformation",
            },
        ],
    },
}

# Used when the chosen topic has no canned content (and as a final fallback).
GENERIC_FALLBACK = {
    "setting": "A curious student and their teacher exploring everyday science.",
    "title": "Thinking Like a Scientist",
    "paragraphs": [
        "Science is all about asking questions and looking carefully at the world around us. A good "
        "scientist notices something curious — like why the sky is blue, or why ice melts — and asks "
        "'why?' and 'how?'.",
        "They make a testable guess, called a hypothesis, and check it with an experiment. By "
        "observing, measuring and recording what happens, we slowly build up reliable knowledge.",
        "Even mistakes are useful, because they tell us what does not work and point us toward better "
        "answers. Every great discovery began with someone curious enough to test their ideas.",
    ],
    "summary": "A scientist asks questions, forms a hypothesis, and tests it with experiments, "
               "learning even from mistakes.",
    "questions": [
        {
            "question": "What do we call a testable guess that we check with an experiment?",
            "options": ["A fact", "A hypothesis", "A conclusion", "A measurement"],
            "correct_index": 1,
            "hint": "It is the idea you form before testing.",
            "concept": "hypothesis",
        },
        {
            "question": "Why are mistakes useful in science?",
            "options": [
                "They are never useful",
                "They show what doesn't work and guide better answers",
                "They prove a scientist should give up",
                "They must always be hidden",
            ],
            "correct_index": 1,
            "hint": "Think about learning from your results.",
            "concept": "scientific method",
        },
    ],
}


def get_mock_chapter(topic, variant_seed=1):
    """Return a canned chapter dict for the given topic title (deep-copied so the
    caller can mutate it freely). `variant_seed` is accepted for forward
    compatibility (more variants could be added later); unused for now."""
    chapter = MOCK_CHAPTERS.get(topic, GENERIC_FALLBACK)
    return copy.deepcopy(chapter)
