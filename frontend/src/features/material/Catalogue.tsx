import { useEffect, useState } from "react";
import { keepPreviousData } from "@tanstack/react-query";
import { Link, useNavigate } from "react-router-dom";

import { client, unwrap } from "../../api/http";
import { useApiMutation, useApiQuery } from "../../api/hooks";
import {
  Badge,
  Button,
  PageHeader,
  QueryBoundary,
  SearchableSelect,
} from "../../components/ui";
import { useCart, WithCart } from "./cart";
import {
  BASE,
  DeficitButton,
  mediaUrl,
  period,
  setTypes,
  useOwnerGroups,
  useTags,
  type ProductTypeCard,
} from "./shared";

/** ``value``, once it has stopped changing for a moment: typing asks the server once, not per key. */
function useSettled<T>(value: T, ms = 250): T {
  const [settled, setSettled] = useState(value);
  useEffect(() => {
    const timer = setTimeout(() => setSettled(value), ms);
    return () => clearTimeout(timer);
  }, [value, ms]);
  return settled;
}

function Availability({ card }: { card: ProductTypeCard }) {
  if (card.set_entries.length > 0) {
    // ``available_direct`` counts the whole sets free without another group's approval.
    const sets = card.sets ?? 0;
    const tone = sets === 0 ? "danger" : card.available_direct === 0 ? "warning" : "success";
    return (
      <span className="availability">
        <Badge tone={tone}>{sets === 1 ? "1 Satz frei" : `${sets} Sätze frei`}</Badge>
        {sets > card.available_direct ? (
          <span className="muted small">{sets - card.available_direct} mit Freigabe</span>
        ) : (
          <span className="muted small">
            {card.total === 1 ? "1 Satz" : `${card.total} Sätze`} aus {card.set_entries.length} Typen
          </span>
        )}
      </span>
    );
  }
  if (card.total === 0) return <span className="muted small">noch keine Teile</span>;
  if (card.sets !== null) {
    return (
      <span className="availability">
        <Badge tone={card.sets === 0 ? (card.available === 0 ? "danger" : "warning") : "success"}>
          {card.sets === 1 ? "1 Satz frei" : `${card.sets} Sätze frei`}
        </Badge>
        <span className="muted small">
          {card.available} / {card.total} Teile
        </span>
      </span>
    );
  }
  const tone = card.available === 0 ? "danger" : card.available_direct === 0 ? "warning" : "success";
  return (
    <span className="availability">
      <Badge tone={tone}>
        {card.available} / {card.total} frei
      </Badge>
      {card.available > card.available_direct && (
        <span className="muted small">
          {card.available - card.available_direct} mit Freigabe
        </span>
      )}
    </span>
  );
}

function TypeCard({ card }: { card: ProductTypeCard }) {
  const cart = useCart();
  return (
    <article className="material-card">
      <Link to={`${BASE}/types/${card.id}`} className="material-card-photo">
        {card.photo ? <img src={mediaUrl(card.photo)} alt="" loading="lazy" /> : <span aria-hidden>◇</span>}
      </Link>
      <div className="material-card-body">
        <Link to={`${BASE}/types/${card.id}`} className="material-card-title">
          {card.name}
        </Link>
        <span className="muted small">
          {[card.manufacturer, card.product_group].filter(Boolean).join(" · ") || " "}
        </span>
        <div className="material-card-tags">
          {card.is_psa && <Badge tone="info">PSA</Badge>}
          {card.tags.map((t) => (
            <Badge key={t.id}>{t.name}</Badge>
          ))}
        </div>
        <div className="material-card-foot">
          <Availability card={card} />
          {card.sets !== null ? (
            <Button
              variant="ghost"
              disabled={card.sets === 0}
              onClick={() =>
                card.set_entries.length > 0
                  ? cart.addSet(card.name, setTypes(card))
                  : cart.addSizes(
                      card.name,
                      card.sizes.map((s) => ({ id: s.id, name: s.name, quantity: s.per_set })),
                    )
              }
              aria-label={`Satz ${card.name} in den Korb`}
            >
              + Satz
            </Button>
          ) : (
            <Button
              variant="ghost"
              disabled={card.available === 0}
              onClick={() => cart.addType({ id: card.id, name: card.name })}
              aria-label={`${card.name} in den Korb`}
            >
              + Korb
            </Button>
          )}
        </div>
      </div>
    </article>
  );
}

/** The material browser: what there is, and how much of it is free in the chosen period. */
export function Catalogue() {
  const cart = useCart();
  const navigate = useNavigate();
  const [q, setQ] = useState("");
  const [tag, setTag] = useState("");
  const [group, setGroup] = useState("");
  const tags = useTags();
  const groups = useOwnerGroups();
  // A group that stops owning material leaves the list; drop it from the filter
  // too, or the catalogue stays filtered by it with no way to clear it.
  useEffect(() => {
    if (group && groups.data && !groups.data.some((g) => String(g.id) === group)) setGroup("");
  }, [group, groups.data]);
  const search = useSettled(q);
  const query = useApiQuery(
    ["material", "types", search, tag, group, cart.start, cart.end],
    () =>
      unwrap(
        client.GET("/api/material/types", {
          params: {
            query: {
              q: search,
              tag: tag ? Number(tag) : undefined,
              group: group ? Number(group) : undefined,
              start: cart.start,
              end: cart.end,
            },
          },
        }),
      ),
    // Keep the cards of the last search on screen while the next one loads.
    { placeholderData: keepPreviousData },
  );

  // A search for a piece's PSA ID offers that piece, above the types it finds.
  const hits = useApiQuery(
    ["material", "parts", "match", search.trim()],
    () =>
      unwrap(client.GET("/api/material/parts/match", { params: { query: { code: search.trim() } } })),
    { enabled: search.trim().length > 0 },
  );

  // Enter on an ID printed on a piece opens that piece; anything else just filters.
  const lookup = useApiMutation(
    (code: string) =>
      unwrap(client.GET("/api/material/parts/lookup", { params: { query: { code } } })),
    { onSuccess: (part) => navigate(`${BASE}/parts/${part.id}`), onError: () => undefined },
  );

  return (
    <div>
      <PageHeader breadcrumbs={[{ label: "Material" }]} subtitle={`Frei ${period(cart.start, cart.end)}`} />
      <WithCart always>
          <div className="list-toolbar">
            <input
              type="search"
              className="list-search"
              aria-label="Material suchen"
              placeholder="Suchen oder ID eingeben…"
              value={q}
              onChange={(e) => setQ(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && q.trim()) lookup.mutate(q.trim());
              }}
            />
            <SearchableSelect
              label="Tag"
              value={tag}
              onChange={setTag}
              options={(tags.data ?? []).map((t) => ({ value: String(t.id), label: t.name }))}
            />
            {/* Only groups owning material are offered; with none, there is nothing to filter by. */}
            {Boolean(groups.data?.length) && (
              <SearchableSelect
                label="Gruppe"
                value={group}
                onChange={setGroup}
                options={(groups.data ?? []).map((g) => ({ value: String(g.id), label: g.name }))}
              />
            )}
          </div>
          {hits.data?.map((part) => (
            <p key={part.id} className="material-hit">
              <Link to={`${BASE}/parts/${part.id}`}>
                Teil <span className="mono">{part.psa_id}</span> – {part.product_type.name}
              </Link>
            </p>
          ))}
          <QueryBoundary query={query} empty="Kein Material gefunden.">
            {(cards) => (
              <div className={`material-grid${query.isPlaceholderData ? " is-stale" : ""}`}>
                {cards.map((card) => (
                  <TypeCard key={card.id} card={card} />
                ))}
              </div>
            )}
          </QueryBoundary>
          <p className="muted small">
            Nicht dabei, was du brauchst? <DeficitButton start={cart.start} end={cart.end} link />
          </p>
      </WithCart>
    </div>
  );
}
