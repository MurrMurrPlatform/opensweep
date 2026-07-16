"""NewsItem + Interest nodes — the repo-scoped radar surface.

NewsItem is what the news-scout agent files from the open web (trending
repos, AI news, frameworks, techniques, research) — grounded in this
repository's stack, tickets, findings, and the user-entered Interests.
News items never become Findings automatically: conversion is a human
action (news_service.convert_to_finding).

Interest is a user-entered topic the scout should watch, on top of what it
derives from the platform data itself.
"""

from neomodel import (
    AsyncStructuredNode,
    BooleanProperty,
    DateTimeProperty,
    JSONProperty,
    StringProperty,
)


class NewsItem(AsyncStructuredNode):
    uid = StringProperty(unique_index=True, required=True)
    repository_uid = StringProperty(required=True, index=True)

    title = StringProperty(required=True)
    url = StringProperty(default="")
    source = StringProperty(default="manual", index=True)
    # searxng | github | hackernews | arxiv | trendshift | manual
    category = StringProperty(default="industry", index=True)
    # trending-repo | ai-news | framework | technique | research | tooling | industry

    summary = StringProperty(default="")
    # Markdown: what the item itself is about.
    relevance = StringProperty(default="")
    # Markdown: why THIS repository's team should care — the field humans triage by.
    tags = JSONProperty(default=[])
    published_at = DateTimeProperty()

    status = StringProperty(default="new", index=True)
    # new | saved | dismissed | converted
    converted_finding_uid = StringProperty(default="")

    dedupe_key = StringProperty(unique_index=True, required=True)
    source_run_uid = StringProperty(index=True)

    created_at = DateTimeProperty(default_now=True)
    updated_at = DateTimeProperty(default_now=True)


class Interest(AsyncStructuredNode):
    uid = StringProperty(unique_index=True, required=True)
    repository_uid = StringProperty(required=True, index=True)

    title = StringProperty(required=True)
    details = StringProperty(default="")
    enabled = BooleanProperty(default=True)

    created_at = DateTimeProperty(default_now=True)
    updated_at = DateTimeProperty(default_now=True)
