import sys
import time
import argparse
from colorama import init, Fore, Style

from daemon.match.matcher import NameMatcher
from daemon.match.intent_classifier import SemanticContextClassifier
from daemon.summary.replies import QuickReplyGenerator

init(autoreset=True)

def run_interactive(name: str = "Mayukh", aliases: list = None, threshold: float = 0.72):
    aliases = aliases or []
    all_names = [name] + [a for a in aliases if a != name]
    
    matcher = NameMatcher(all_names, threshold=threshold)
    classifier = SemanticContextClassifier()
    reply_gen = QuickReplyGenerator()

    print(f"\n{Fore.CYAN}{Style.BRIGHT}{'='*68}")
    print(f"  BECKON INTERACTIVE TERMINAL SIMULATOR (Zero Android Studio Needed)")
    print(f"  Target: {Fore.GREEN}{name}{Fore.CYAN} | Aliases: {Fore.YELLOW}{aliases or 'None'}{Fore.CYAN} | Threshold: {threshold}")
    print(f"{'='*68}{Style.RESET_ALL}")
    print(f"{Fore.WHITE}Type any sentence as if spoken in a meeting (English, Bengali, Hindi).")
    print(f"Commands: {Fore.YELLOW}!name <new_name>{Fore.WHITE} to change target | {Fore.YELLOW}exit{Fore.WHITE} or {Fore.YELLOW}quit{Fore.WHITE} to stop.\n")

    default_samples = [
        f"Hey {name}, can you take over screen sharing for a minute?",
        f"I think {name} mentioned something about that in yesterday's call.",
        f"{name}, are you free to look at this pull request?",
        f"{name} ke jiggesh koro o ki bolchhe.",
        f"Suno {name}, tum meeting me ho kya?"
    ]

    print(f"{Fore.MAGENTA}Try typing one of these examples:")
    for s in default_samples:
        print(f"  {Fore.LIGHTBLACK_EX}• \"{s}\"")
    print(f"{Style.RESET_ALL}")

    while True:
        try:
            user_input = input(f"{Fore.GREEN}beckon> {Style.RESET_ALL}").strip()
        except (KeyboardInterrupt, EOFError):
            print(f"\n{Fore.YELLOW}Exiting interactive simulator.{Style.RESET_ALL}")
            break

        if not user_input:
            continue

        if user_input.lower() in {"exit", "quit", "q"}:
            print(f"{Fore.YELLOW}Goodbye!{Style.RESET_ALL}")
            break

        if user_input.startswith("!name "):
            parts = user_input.split(" ", 1)
            if len(parts) > 1 and parts[1].strip():
                name = parts[1].strip()
                all_names = [name]
                matcher = NameMatcher(all_names, threshold=threshold)
                print(f"{Fore.CYAN}Target name updated to: {Fore.GREEN}{name}{Style.RESET_ALL}\n")
            continue

        # Benchmark inference time
        t0 = time.perf_counter()
        match_res = matcher.evaluate_text(user_input)
        is_matched = match_res is not None and match_res.matched
        
        target_eval = match_res.target_name if match_res else name
        intent_res = classifier.classify(user_input, target_eval)
        elapsed_ms = (time.perf_counter() - t0) * 1000

        print(f"\n  {Fore.WHITE}{Style.BRIGHT}Transcription:{Style.RESET_ALL} \"{user_input}\"")

        if not is_matched:
            print(f"  {Fore.LIGHTBLACK_EX}[STATUS] ⚪ NO TARGET NAME DETECTED ({elapsed_ms:.2f}ms)")
            if match_res and match_res.score > 0:
                print(f"  {Fore.LIGHTBLACK_EX}Score: {match_res.score:.2f} (below threshold {threshold})")
            print()
            continue

        # Matched target name
        score = match_res.score
        matched_target = match_res.target_name

        if intent_res.is_direct_address:
            # Generate quick replies
            replies = reply_gen.generate_replies(user_input, matched_target)

            print(f"  {Fore.RED}{Style.BRIGHT}🚨 [STATUS] ALERT DISPATCHED! (Direct Vocative Address)")
            print(f"  {Fore.CYAN}⚡ Engine Latency:  {Fore.WHITE}{elapsed_ms:.2f}ms")
            print(f"  {Fore.CYAN}🎯 Matched Target:  {Fore.GREEN}{matched_target} {Fore.CYAN}(Confidence: {score:.2f})")
            print(f"  {Fore.CYAN}🗣️ Intent Reason:   {Fore.WHITE}{intent_res.intent} (Conf: {intent_res.confidence:.2f})")
            if intent_res.signals:
                print(f"  {Fore.CYAN}🔍 Linguistic Cues: {Fore.LIGHTYELLOW_EX}{', '.join(intent_res.signals)}")
            
            print(f"\n  {Fore.GREEN}{Style.BRIGHT}💡 Contextual Quick-Replies (One-Tap Pills):")
            for i, r in enumerate(replies, 1):
                print(f"     {Fore.LIGHTGREEN_EX}[{i}] \"{r}\"")
        else:
            print(f"  {Fore.YELLOW}{Style.BRIGHT}🔕 [STATUS] SUPPRESSED (3rd-Person / Non-Vocative Reference)")
            print(f"  {Fore.CYAN}⚡ Engine Latency:  {Fore.WHITE}{elapsed_ms:.2f}ms")
            print(f"  {Fore.CYAN}🎯 Mentioned Name:  {Fore.YELLOW}{matched_target} {Fore.CYAN}(Confidence: {score:.2f})")
            print(f"  {Fore.CYAN}🗣️ Intent Reason:   {Fore.LIGHTRED_EX}{intent_res.intent} (Conf: {intent_res.confidence:.2f})")
            if intent_res.signals:
                print(f"  {Fore.CYAN}🔍 Linguistic Cues: {Fore.LIGHTYELLOW_EX}{', '.join(intent_res.signals)}")
            print(f"  {Fore.LIGHTBLACK_EX}ℹ️  Beckon withheld vibration/sound to prevent distraction.")

        print()

def main():
    parser = argparse.ArgumentParser(description="Beckon Interactive Terminal Simulator")
    parser.add_argument("--name", default="Mayukh", help="Target canonical name (default: Mayukh)")
    parser.add_argument("--aliases", nargs="*", default=[], help="Optional nicknames / aliases")
    parser.add_argument("--threshold", type=float, default=0.72, help="Matching sensitivity threshold (default: 0.72)")
    args = parser.parse_args()

    run_interactive(name=args.name, aliases=args.aliases, threshold=args.threshold)

if __name__ == "__main__":
    main()
