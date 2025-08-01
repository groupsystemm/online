# utils.py
def calculate_total(mid, final, assignment, quiz):
    return round(mid * 0.3 + final * 0.4 + assignment * 0.2 + quiz * 0.1, 2)

def letter_grade(total):
    if total >= 92: return "A+"
    elif total >= 85: return "A"
    elif total >= 75: return "B+"
    elif total >= 65: return "B"
    elif total >= 50: return "C"
    else: return "F"
