# rules.py
# The rule engine: plain Python rules (no LLM) that decide whether two reported
# results can be compared. Each pair gets four checks (task, dataset, metric,
# evaluation settings), then the checks are combined into one of three labels.

import re

# The three labels the rule engine can return
NOT_COMPARABLE = "not_directly_comparable"
POTENTIALLY_COMPARABLE = "potentially_comparable"
NOT_ENOUGH_INFO = "not_enough_information"

# How much two descriptions must overlap (0 to 1) to count as a match.
# These are starting guesses, tune them on real examples.
TASK_MATCH = 0.4
SETTINGS_MATCH = 0.6

# Common function words we ignore when comparing text.
# Words like "not", "only", "same" are kept on purpose because they change the meaning.
STOP_WORDS = {
    "the", "a", "an", "of", "to", "and", "in", "on", "for", "with", "from", "is",
    "are", "by", "at", "using", "that", "this", "these", "those", "which", "as",
    "be", "been", "it", "its", "or", "we", "our", "their", "was", "were", "has",
    "have", "can", "also", "into", "than", "then", "such", "each", "how", "what",
    "when", "where", "who", "about", "through", "across", "will", "would", "could",
    "should", "may", "might", "used", "use", "based",
}

# Filler in metric names ("Pearson's correlation coefficient" = "Pearson correlation")
METRIC_FILLER = {"s", "coefficient", "score", "metric"}

# Words that change how a metric is calculated or reported. If two results have the same
# metric name but different words from this list, they are not defined the same way.
# Starting list, add more as we run into them in other fields.
QUALIFIER_WORDS = ["macro", "micro", "weighted", "adjusted", "unadjusted", "median"]

# Words that do not help identify a dataset
DATASET_FILLER = {"dataset", "datasets", "data", "set"}

# Names of datasets we know are separate from each other. Only used to say two datasets
# are DIFFERENT. Starts empty. Add the datasets from the papers chosen for the evaluation.
KNOWN_DATASETS = []


# ---------- Small helpers ----------

def normalize(text):
    # Lowercase, and turn anything that is not a letter or digit into a space
    return re.sub(r"[^a-z0-9]+", " ", str(text).lower()).strip()


def is_missing(text):
    # True if the paper did not report this (or it is empty)
    return text is None or normalize(text) in ("", "not reported")


def word_overlap(text_a, text_b):
    # Shared words divided by all words used (0 = nothing in common, 1 = identical)
    # Returns None if one side has no useful words left, so we can say "unknown"
    words_a = set(normalize(text_a).split()) - STOP_WORDS
    words_b = set(normalize(text_b).split()) - STOP_WORDS
   
    if not words_a or not words_b:
        return None
    
    return len(words_a & words_b) / len(words_a | words_b)


def dataset_words(name):
    # The words that identify a dataset (word order and filler words do not matter)
    return set(normalize(name).split()) - DATASET_FILLER


# ---------- The four checks (each returns a status and a reason) ----------
# status is "match", "mismatch", or "unknown" (not enough information)

def check_task(task_a, task_b):
    if is_missing(task_a) or is_missing(task_b):
        return "unknown", "At least one paper does not report its research task."

    # Word overlap can tell us two tasks are similar, but not that they are different
    # (related papers can describe their tasks with completely different words)
    score = word_overlap(task_a, task_b)

    if score is not None and score >= TASK_MATCH:
        return "match", "The two task descriptions share many words."
    
    return "unknown", "Cannot tell whether the tasks are the same or closely related."


def find_known_dataset(name):
    # Returns the matching name from our list, or None if it is not on the list
    words = dataset_words(name)

    for known in KNOWN_DATASETS:
        if words == dataset_words(known):
            return known
        
    return None


def check_dataset(dataset_a, dataset_b):
    if is_missing(dataset_a) or is_missing(dataset_b):
        return "unknown", "At least one result does not report its dataset."

    words_a = dataset_words(dataset_a)
    words_b = dataset_words(dataset_b)
    if words_a and words_a == words_b:
        return "match", "Same dataset name (this does not guarantee the same version or subset)."

    # Different names: only call them different if we know both are separate datasets
    if find_known_dataset(dataset_a) and find_known_dataset(dataset_b):
        return "mismatch", f"Different datasets: {dataset_a} and {dataset_b}."

    # Otherwise we do not guess
    return "unknown", f"Cannot tell whether '{dataset_a}' and '{dataset_b}' are the same dataset."


def clean_metric_name(metric):
    words = [w for w in normalize(metric).split() if w not in METRIC_FILLER]
    return " ".join(words)


def qualifiers_used(metric, definition):
    # Which qualifier words show up in the metric name or its definition
    words = normalize(f"{metric} {definition}").split()
    return {w for w in QUALIFIER_WORDS if w in words}


def check_metric(result_a, result_b):
    metric_a = result_a.get("metric")
    metric_b = result_b.get("metric")
    if is_missing(metric_a) or is_missing(metric_b):
        return "unknown", "At least one result does not report its metric."

    if clean_metric_name(metric_a) != clean_metric_name(metric_b):
        return "mismatch", f"Different metrics: {metric_a} and {metric_b}."

    # Same name, so check whether they are defined the same way
    qualifiers_a = qualifiers_used(metric_a, result_a.get("metric_definition", ""))
    qualifiers_b = qualifiers_used(metric_b, result_b.get("metric_definition", ""))

    if qualifiers_a and qualifiers_b and qualifiers_a != qualifiers_b:
        return "mismatch", "Same metric name but defined differently (for example macro vs weighted, or adjusted vs unadjusted)."
    
    if qualifiers_a != qualifiers_b:
        return "unknown", "Only one result says how the metric is defined or adjusted."
    
    return "match", "Same metric."


def check_settings(settings_a, settings_b):
    if is_missing(settings_a) or is_missing(settings_b):
        return "unknown", "At least one result does not report its evaluation settings."

    score = word_overlap(settings_a, settings_b)
    if normalize(settings_a) == normalize(settings_b) or (score is not None and score >= SETTINGS_MATCH):
        return "match", "The evaluation settings look the same."

    # Different wording does not prove the settings are incompatible, so we do not guess
    return "unknown", "The settings are worded differently, so we cannot tell if they are compatible."


# ---------- Putting the checks together ----------

def compare_results(task_a, result_a, task_b, result_b):
    # Run all four checks
    checks = {
        "task": check_task(task_a, task_b),
        "dataset": check_dataset(result_a.get("dataset"), result_b.get("dataset")),
        "metric": check_metric(result_a, result_b),
        "evaluation_settings": check_settings(result_a.get("evaluation_settings"),
                                              result_b.get("evaluation_settings")),
    }
    statuses = [checks[name][0] for name in checks]

    # Order matters: a known mismatch beats missing information
    if "mismatch" in statuses:
        label = NOT_COMPARABLE

    elif "unknown" in statuses:
        label = NOT_ENOUGH_INFO
    
    else:
        label = POTENTIALLY_COMPARABLE

    # Collect the reasons for anything that did not match
    reasons = []
    check_details = {}

    for name in checks:
        status, reason = checks[name]
        check_details[name] = {"status": status, "reason": reason}

        if status != "match":
            reasons.append(f"{name}: {reason}")
            
    if label == POTENTIALLY_COMPARABLE:
        reasons.append("All four checks matched. This only means the results may be comparable, not that one is better.")

    return {"label": label, "reasons": reasons, "checks": check_details}