# MemPalace Search

When the user wants to search their MemPalace memories, follow these steps:

## 1. Parse the Search Query

Extract the core search intent from the user's message. Identify any explicit
or implicit filters:
- Wing -- a top-level category (e.g., "work", "personal", "research")
- Room -- a sub-category within a wing
- Keywords / semantic query -- the actual search terms

## 2. Determine Wing/Room Filters

If the user mentions a specific domain, topic area, or context, map it to the
appropriate wing and/or room. If unsure, omit filters to search globally. You
can discover the taxonomy first if needed.

## 3. Use MCP Tools (Preferred)

If MCP tools are available, use them in this priority order:

- mempalace_search(query, wing, room) -- Primary search tool. Pass the semantic
  query and any wing/room filters.
- mempalace_list_wings -- Discover all available wings. Use when the user asks
  what categories exist or you need to resolve a wing name.
- mempalace_list_rooms(wing) -- List rooms within a specific wing. Use to help
  the user navigate or to resolve a room name.
- mempalace_get_taxonomy -- Retrieve the full wing/room/drawer tree. Use when
  the user wants an overview of their entire memory structure.
- mempalace_traverse(room) -- Walk the knowledge graph starting from a room.
  Use when the user wants to explore connections and related memories.
- mempalace_find_tunnels(wing1, wing2) -- Find cross-wing connections (tunnels)
  between two wings. Use when the user asks about relationships between
  different knowledge domains.

## 4. Low-Token Retrieval Strategy

Keep retrieval cheap by default. Prefer a few short searches over one large
dump.

Recommended order:

1. Run one short natural-language query with a small limit (`3` to `5`).
2. If the top result is weak or ambiguous, run a second query using only the
   core keywords.
3. Only if still needed, run a third query with synonyms, aliases, or
   alternate wording (including PT/EN variants when relevant).

Additional rules:
- Do not fetch `10+` results unless the task truly needs broad review.
- Do not call taxonomy discovery tools by reflex; use them only when wing/room
  mapping is blocked.
- For durable facts, prefer `mempalace_kg_query` before broad search.
- For recent work, decisions, handoff, or session history, prefer diary search
  (`mempalace_diary_read` or room=`diary`) before wider retrieval.
- Start broad, then narrow with wing/room only after you have a concrete lead.
- If the first search is weak, reformulate. Do not pretend the first hit is
  good enough.

## 5. CLI Fallback

If MCP tools are not available, fall back to the CLI:

    mempalace search "query" [--wing X] [--room Y]

## 6. Present Results

When presenting search results:
- Always include source attribution: wing, room, and drawer for each result
- Show relevance or similarity scores if available
- Group results by wing/room when returning multiple hits
- Quote or summarize the memory content clearly

## 7. Offer Next Steps

After presenting results, offer the user options to go deeper:
- Drill deeper -- search within a specific room or narrow the query
- Traverse -- explore the knowledge graph from a related room
- Check tunnels -- look for cross-wing connections if the topic spans domains
- Browse taxonomy -- show the full structure for manual exploration
