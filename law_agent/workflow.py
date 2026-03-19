"""Legal Obligation Extractor — Hush Workflow.

Usage:
  uv run python -m law_agent.workflow <document.docx> [output.json] [max_articles]

Re-run same command to retry failed articles. Already-classified articles
skip the classify LLM call. Already-done articles are skipped entirely.
"""

import asyncio
import sys

from dotenv import load_dotenv

load_dotenv()

from hush.core import Hush, GraphOp, START, END, PARENT
from hush.core.ops.flow import if_
from hush.providers import chain

from law_agent.ops import (
    read_doc, chunk_and_save, parse_and_prepare,
    save_classify, save_actions,
)
from law_agent.prompts import CLASSIFY_SYSTEM, CLASSIFY_USER, ACTION_SYSTEM, ACTION_USER

# =============================================================================
# Workflow graph
# =============================================================================

with GraphOp(name="law-extractor", concurrency=2) as graph:
    # Read document
    doc = read_doc(file_path=PARENT["file_path"])

    # Chunk and save to JSON (generator — yields articles needing work)
    articles = chunk_and_save(
        text=doc["text"],
        metadata=doc["metadata"],
        output_path=PARENT["output_path"],
        max_articles=PARENT["max_articles"],
    )

    # Branch — skip classify if already classified
    router = (
        if_(articles["skip_classify"] == True, "prepared")
        .else_("classify")
    )

    # Classify (LLM) + save to JSON
    classify = chain(
        resource="gpt-4o",
        template={"system": CLASSIFY_SYSTEM, "user": CLASSIFY_USER},
        article_text=articles["text"],
        response_format={"type": "json_object"},
    )
    sc = save_classify(
        article_id=articles["article_id"],
        output_path=articles["output_path"],
        classified_json=classify["content"],
    )

    # Prepare: merge classify result from either branch
    # - classify path: sc["classified_json"] (fresh from LLM)
    # - skip path: articles["classified_json"] (cached from JSON)
    prepared = parse_and_prepare(
        article_id=articles["article_id"],
        title=articles["title"],
        text=articles["text"],
        output_path=articles["output_path"],
        classify_content=sc["classified_json"],
        cached_content=articles["classified_json"],
    )

    # Generate actions (LLM)
    actions = chain(
        resource="gpt-4o",
        template={"system": ACTION_SYSTEM, "user": ACTION_USER},
        article_text=prepared["safe_text"],
        dieu_keys=prepared["dieu_keys"],
        response_format={"type": "json_object"},
    )

    # Save final result
    result = save_actions(
        article_id=prepared["article_id"],
        output_path=prepared["output_path"],
        classified_json=prepared["classified_json"],
        actions_content=actions["content"],
    )

    # Wiring
    START >> doc >> articles >> router
    router >> classify >> sc
    router >>~ prepared
    sc >>~ prepared
    prepared >> actions >> result >> END


# =============================================================================
# CLI
# =============================================================================

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: uv run python -m law_agent.workflow <document.docx> [output.json] [max_articles]")
        sys.exit(1)

    file_path = sys.argv[1]
    output_path = sys.argv[2] if len(sys.argv) > 2 else file_path.rsplit(".", 1)[0] + ".json"
    max_articles = int(sys.argv[3]) if len(sys.argv) > 3 else -1

    async def main():
        engine = Hush(graph, resources="resources.yaml")
        await engine.run({
            "file_path": file_path,
            "output_path": output_path,
            "max_articles": max_articles,
        })
        print(f"Done. Results saved to {output_path}")

    asyncio.run(main())
