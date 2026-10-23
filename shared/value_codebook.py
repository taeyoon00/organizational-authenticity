"""
Value categories used to code BOTH stated values (Part 1, About pages) and
disclosed values (Part 2). Using one codebook for both is what lets Part 3
compare them in the same space. Rationale: DECISIONS.md, D-008.

Categories 1-9 are the MIT Sloan / Glassdoor Culture 500 "Big Nine" values
(Sull, Turconi & Sull 2019), derived empirically from how employees and
firms describe culture. Categories 10-12 cover stakeholder themes that ESG,
DEI and proxy disclosures report on and that the Big Nine fold into other
categories or omit.

Each entry: definition used in the LLM prompt, and examples of language that
counts / does not count, to keep the boundaries between neighbours explicit.
"""

CODEBOOK = {
    "agility": {
        "label": "Agility",
        "definition": "Speed, adaptability and responsiveness to change; nimbleness, flexibility, willingness to change course.",
        "counts": "move fast, adapt, embrace change, nimble, act with urgency",
        "not": "innovation of new products (-> innovation)",
    },
    "collaboration": {
        "label": "Collaboration",
        "definition": "Teamwork and cooperation inside the firm and with partners.",
        "counts": "teamwork, one team, partnership, work together, collaborate across boundaries",
        "not": "serving customers (-> customer); community partnerships (-> community)",
    },
    "customer": {
        "label": "Customer",
        "definition": "Putting customers, clients or patients at the centre; service quality and customer success.",
        "counts": "customer obsession, client first, patients first, serve our guests, customer success",
        "not": "general statements about society or communities (-> community)",
    },
    "diversity_inclusion": {
        "label": "Diversity & Inclusion",
        "definition": "Diversity of people and perspectives, equity, inclusion and belonging.",
        "counts": "diverse workforce, inclusion, belonging, equity, equal opportunity, DEI",
        "not": "respectful treatment without reference to diversity (-> respect)",
    },
    "execution": {
        "label": "Execution",
        "definition": "Operational excellence, discipline, accountability for delivering results, quality of work.",
        "counts": "excellence, accountability, ownership, deliver results, operational discipline, quality, safety as an operating standard",
        "not": "financial or market outcomes (-> performance)",
    },
    "innovation": {
        "label": "Innovation",
        "definition": "Creating new products, technologies or ideas; pioneering, research, creativity.",
        "counts": "innovate, pioneer, breakthrough science, invent, research, creativity, technology leadership",
        "not": "adapting quickly to change (-> agility)",
    },
    "integrity": {
        "label": "Integrity",
        "definition": "Honesty, ethics, transparency, doing the right thing, compliance with laws and standards.",
        "counts": "integrity, ethics, honesty, trust, transparency, do the right thing, highest standards of conduct",
        "not": "treating people with dignity (-> respect)",
    },
    "performance": {
        "label": "Performance",
        "definition": "Results orientation in financial and market terms: growth, profitability, shareholder value, winning, leadership position.",
        "counts": "shareholder value, growth, returns, market leader, win, high performance, competitive",
        "not": "doing work well or reliably (-> execution)",
    },
    "respect": {
        "label": "Respect",
        "definition": "Treating people with dignity, consideration and courtesy; valuing employees and others as individuals.",
        "counts": "respect, dignity, treat each other well, care for one another, value every voice",
        "not": "diversity or inclusion language (-> diversity_inclusion)",
    },
    "environment_sustainability": {
        "label": "Environment & Sustainability",
        "definition": "Environmental responsibility: climate, emissions, energy transition, resource use, protecting the planet.",
        "counts": "sustainability, climate, net zero, emissions, renewable, environmental stewardship, planet",
        "not": "long-term business continuity without an environmental meaning",
    },
    "community_social_impact": {
        "label": "Community & Social Impact",
        "definition": "Contribution to communities and society beyond customers: philanthropy, volunteering, access, social progress.",
        "counts": "communities, give back, philanthropy, social impact, improve lives, access to health/finance, citizenship",
        "not": "customers or patients as buyers of products (-> customer)",
    },
    "employee_wellbeing_development": {
        "label": "Employee Wellbeing & Development",
        "definition": "Investing in employees: wellbeing, health and safety of the workforce, growth, learning, careers, benefits.",
        "counts": "develop our people, learning, careers, wellbeing, employee health and safety, great place to work",
        "not": "diversity of the workforce (-> diversity_inclusion); respectful treatment (-> respect)",
    },
}

CATEGORY_IDS = list(CODEBOOK)

# Dictionary version of the codebook (regular expressions, case-insensitive).
# Used to code disclosure documents in Part 2 and as a second, transparent
# coder for the LLM in Part 1. Patterns avoid common legal / proxy phrases
# that would otherwise be counted ("equity awards", "with respect to",
# "respectively", "execution of this agreement").
LEXICON = {
    "agility": r"\bagil(e|ity)\b|\bnimble\b|\badaptab\w*|\badapt(ing|s)? to change\b|\bspeed to market\b|\bmove fast\b",
    "collaboration": r"\bcollaborat\w*|\bteamwork\b|\bone team\b|\bwork(ing)? together\b",
    "customer": r"\bcustomers?\b|\bclients?\b|\bpatients?\b|\bconsumers?\b|\bguests?\b",
    "diversity_inclusion": r"\bdivers(e|ity)\b|\binclusi(on|ve|vity)\b|\bbelonging\b|\bunderrepresented\b|\bequal opportunit\w*|\bpay equity\b|\bequitable\b|\bDE&I\b|\bDEI\b",
    "execution": r"\boperational excellence\b|\baccountab\w*|\bdisciplin(e|ed)\b(?! action)|\bexecut(e|ing) (on |our |the )?strateg\w*|\bhigh[- ]quality\b|\bexcellence\b",
    "innovation": r"\binnovat\w*|\binvent\w*|\bpioneer\w*|\bbreakthrough\w*|\bresearch and development\b|\bR&D\b",
    "integrity": r"\bintegrity\b|\bethic(s|al|ally)\b|\bhonest\w*|\btransparen\w*|\bcode of (business )?conduct\b|\bdo(ing)? the right thing\b",
    "performance": r"\bshareholder value\b|\btotal shareholder return\b|\bTSR\b|\bprofitab\w*|\bearnings growth\b|\brevenue growth\b|\boutperform\w*|\bfinancial performance\b|\bhigh[- ]performance\b",
    "respect": r"(?<!with )(?<!in )\brespect(ful|fully|ed|ing)?\b(?! (to|of)\b)|\bdignity\b|\bcivility\b",
    "environment_sustainability": r"\bsustainab\w*|\bclimate\b|\bemissions?\b|\bnet[- ]zero\b|\brenewable\w*|\benvironment(al)?\b|\bcarbon\b|\bgreenhouse\b",
    "community_social_impact": r"\bcommunit(y|ies)\b|\bphilanthrop\w*|\bvolunteer\w*|\bcharit(y|able|ies)\b|\bsocial impact\b|\bgiv(e|ing) back\b",
    "employee_wellbeing_development": r"\bhuman capital\b|\btalent development\b|\bcareer (development|growth)\b|\bwell[- ]?being\b|\bemployee (engagement|health|development|training)\b|\btraining\b|\bupskill\w*|\breskill\w*",
}


def codebook_text():
    """The codebook rendered for an LLM prompt (stable text, so it caches)."""
    lines = []
    for cid, c in CODEBOOK.items():
        lines.append(f"- {cid} ({c['label']}): {c['definition']}\n"
                     f"    counts: {c['counts']}\n    does not count: {c['not']}")
    return "\n".join(lines)
