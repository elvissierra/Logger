
<script setup>
import { ref, nextTick } from 'vue'
import TimeCard from './TimeCard.vue'

// Constant headroom policy: show up to N previous entries peeking above the front card.
// This keeps cell layouts uniform regardless of how many entries exist.
const MAX_DECK_BEHIND = 3

// Hovered deck entry state (scoped to the hovered deck only)
const hoveredEntryId = ref(null)       // String(id)
const hoveredEntryIdx = ref(null)      // 1..n (within the behind stack)
const hoveredDeckId = ref(null)        // `${laneKey}|${dayKey}`
const hoverDeltaPx = ref(0)            // how much to push the cards in front (px)

let _hoverToken = 0

let _leaveTimer = null

function _clearLeaveTimer() {
  if (_leaveTimer) {
    clearTimeout(_leaveTimer)
    _leaveTimer = null
  }
}

function _parsePx(v) {
  const n = parseFloat(String(v || '').trim())
  return Number.isFinite(n) ? n : 0
}

async function onDeckEnter(e, entryId, entryIdx, deckId) {
  _hoverToken += 1
  const token = _hoverToken
  _clearLeaveTimer()

  hoveredEntryId.value = String(entryId)
  hoveredEntryIdx.value = Number(entryIdx)
  hoveredDeckId.value = String(deckId)

  // Wait for Vue to re-render the hovered card with `collapsed=false`.
  await nextTick()
  if (token !== _hoverToken) return

  const el = e?.currentTarget
  if (!el) return

  // Deck peek height is controlled by CSS var on .deck
  const deckEl = el.closest('.deck')
  const peekPx = deckEl
    ? _parsePx(getComputedStyle(deckEl).getPropertyValue('--deck-peek'))
    : _parsePx(getComputedStyle(el).height)

  // Expanded height: use scrollHeight (works even if height is auto)
  const expandedPx = Math.max(
    _parsePx(el.scrollHeight),
    _parsePx(el.getBoundingClientRect?.().height)
  )

  // Push only by the extra height needed beyond the peek.
  hoverDeltaPx.value = Math.max(0, expandedPx - peekPx)
}


function onDeckLeave() {
  // Debounce collapse so quick pointer transitions inside the deck don’t flicker.
  _clearLeaveTimer()
  const tokenAtLeave = ++_hoverToken

  _leaveTimer = setTimeout(() => {
    if (tokenAtLeave !== _hoverToken) return
    hoveredEntryId.value = null
    hoveredEntryIdx.value = null
    hoveredDeckId.value = null
    hoverDeltaPx.value = 0
  }, 90)
}

function onFrontEnter(deckId) {
  _clearLeaveTimer()
  // Bump token so any pending measurements from a prior hover can't apply.
  _hoverToken += 1

  const id = String(deckId || '')
  if (hoveredDeckId.value && hoveredDeckId.value === id) {
    hoveredEntryId.value = null
    hoveredEntryIdx.value = null
    hoveredDeckId.value = null
    hoverDeltaPx.value = 0
  }
}

const props = defineProps({
  // container state
  layoutMode: { type: String, required: true },
  headerDays: { type: Array, required: true },
  swimlanes: { type: Array, required: true },

  // timer + ticking
  runningId: { required: true },
  nowTick: { required: true },
  incrementMinutes: { type: Number, required: true },

  // formatters / aggregations
  fmtH: { type: Function, required: true },
  colHours: { type: Function, required: true },
  laneHours: { type: Function, required: true },
  laneEntryCount: { type: Function, required: true },
  cellHours: { type: Function, required: true },

  // lane helpers
  getLaneMeta: { type: Function, required: true },
  laneDesc: { type: Function, required: true },
  isLaneRunning: { type: Function, required: true },

  // lane meta editor state + actions (owned by TimeBoard)
  priorities: { type: Array, required: true },
  laneMetaDraft: { required: true },
  isEditingLaneMeta: { type: Function, required: true },
  editLaneMeta: { type: Function, required: true },
  saveLaneMeta: { type: Function, required: true },
  cancelLaneMetaEdit: { type: Function, required: true },

  // entry actions
  startLaneTimer: { type: Function, required: true },
  startTimer: { type: Function, required: true },
  stopTimer: { type: Function, required: true },
  addCard: { type: Function, required: true },
  saveCard: { type: Function, required: true },
  deleteCard: { type: Function, required: true },
  onCellChange: { type: Function, required: true },
  onReorderCell: { type: Function, required: true },
})

const PRIORITIES = props.priorities
</script>

<template>
  <!-- Weekly Board/Grid: 7-day matrix with swimlanes on rows; entries rendered only when present in a cell. -->
  <div class="board__scroller" v-if="layoutMode==='grid'">
    <h2 class="board__sectiontitle">Weekly log</h2>

    <div class="grid">
      <!-- Header row -->
      <div class="cell cell--head"></div>
      <div v-for="d in headerDays" :key="d.key" class="cell cell--head">
        <div class="dayhead">
          <strong>{{ d.label }}</strong>
          <small>{{ fmtH(colHours(d.key), 2) }} h</small>
        </div>
      </div>

      <!-- Swimlane rows (folder-style lanes) -->
      <section
        v-for="lane in swimlanes"
        :key="lane.key"
        class="laneRow"
        :class="'prio-' + String((getLaneMeta(lane.key).priority || 'Normal')).toLowerCase()"
      >
        <div class="laneRow__grid">
          <div class="cell cell--rowhead">
            <article
              class="projcard"
              :class="'prio-' + String((getLaneMeta(lane.key).priority || 'Normal')).toLowerCase()"
            >
              <header class="projcard__head">
                <h4
                  class="title"
                  :title="lane.title + (laneDesc(lane.key) ? ' — ' + laneDesc(lane.key) : '')"
                >
                  {{ lane.title }}
                </h4>
                <span
                  v-if="isLaneRunning(lane)"
                  class="projcard__running-icon"
                  title="Timer running"
                  aria-label="Timer running"
                >
                  ⏱️
                </span>
              </header>

              <div class="projcard__hoursrow">
                <span class="projcard__hours-pill">{{ fmtH(laneHours(lane), 2) }} h</span>
                <span v-if="laneEntryCount(lane)" class="projcard__entries">
                  {{ laneEntryCount(lane) }} entr<span v-if="laneEntryCount(lane) !== 1">ies</span>
                </span>
              </div>

              <footer class="projcard__foot">
                <div class="spacer"></div>
                <div class="actions__icons">
                  <button
                    class="mini icon"
                    @click="isLaneRunning(lane) ? stopTimer() : startLaneTimer(lane)"
                    :title="isLaneRunning(lane) ? 'Stop timer' : 'Start timer'"
                  >
                    {{ isLaneRunning(lane) ? '■' : '▶︎' }}
                  </button>
                  <button
                    class="mini icon"
                    @click="editLaneMeta(lane)"
                    title="Edit project settings"
                  >
                    ⋯
                  </button>
                </div>
              </footer>

              <div v-if="isEditingLaneMeta(lane.key)" class="lane-meta-editor lane-meta-editor--row">
                <label class="lane-meta-editor__field">
                  <span>Priority</span>
                  <select v-model="laneMetaDraft.priority">
                    <option v-for="p in PRIORITIES" :key="p" :value="p">{{ p }}</option>
                  </select>
                </label>

                <label class="lane-meta-editor__field">
                  <span>Description</span>
                  <textarea
                    v-model="laneMetaDraft.description"
                    rows="2"
                    placeholder="Short description for this lane"
                  ></textarea>
                </label>

                <div class="lane-meta-editor__actions">
                  <button type="button" class="mini" @click="saveLaneMeta(lane)">Save</button>
                  <button type="button" class="mini" @click="cancelLaneMetaEdit">Cancel</button>
                </div>
              </div>
            </article>
          </div>

          <!-- Day cells -->
          <template v-for="col in lane.columns" :key="lane.key + ':' + col.dayKey">
            <div class="cell">
              <div class="cell__sum" v-if="cellHours(lane, col.dayKey)">
                {{ fmtH(cellHours(lane, col.dayKey), 2) }} h
              </div>
              <div class="cell__actions">
                <button class="mini icon" @click="addCard(lane, col)" title="Add card to this cell">＋</button>
              </div>

              <div v-if="col.cards.length" class="droplist">
                <div
                  class="deck"
                  :data-deck-id="lane.key + '|' + col.dayKey"
                  :class="{ 'deck--hovering': hoveredDeckId === (lane.key + '|' + col.dayKey) }"
                  :style="{
                    '--deck-front-push': (hoveredDeckId === (lane.key + '|' + col.dayKey) && hoveredEntryIdx)
                      ? (hoverDeltaPx + 'px')
                      : '0px'
                  }"
                  @mouseleave="onDeckLeave"
                >
                  <!-- Front / current entry (newest) -->
                  <div
                    v-if="col.cards[0]"
                    class="deckFront"
                    @mouseenter="onFrontEnter(lane.key + '|' + col.dayKey)"
                  >
                    <TimeCard
                      :card="col.cards[0]"
                      :open-on-mount="col.cards[0].__new === true"
                      :running-id="runningId"
                      :now-tick="nowTick"
                      :compact="true"
                      :stack-index="0"
                      :tab-side="'left'"
                      :collapsed="false"
                      :increment-minutes="incrementMinutes"
                      @start="startTimer"
                      @stop="stopTimer"
                      @save="saveCard"
                      @delete="c => deleteCard(lane, col, c)"
                    />
                  </div>
                  <!-- Previous entries: above + behind; title-only until hover -->
                  <div class="deckBehind" v-if="col.cards.length > 1">
                    <div
                      v-for="(element, i) in col.cards.slice(1, 1 + MAX_DECK_BEHIND)"
                      :key="element.id"
                      :class="[
                        'deckItem',
                        (hoveredDeckId === (lane.key + '|' + col.dayKey) && hoveredEntryId === String(element.id))
                          ? 'deckItem--active'
                          : ''
                      ]"
                      :style="{
                        '--deck-i': (i + 1),
                        '--deck-push': (hoveredDeckId === (lane.key + '|' + col.dayKey) && hoveredEntryIdx && ((i + 1) < hoveredEntryIdx))
                          ? (hoverDeltaPx + 'px')
                          : '0px'
                      }"
                      @mouseenter="onDeckEnter($event, element.id, (i + 1), (lane.key + '|' + col.dayKey))"
                    >
                      <TimeCard
                        :card="element"
                        :open-on-mount="element.__new === true"
                        :running-id="runningId"
                        :now-tick="nowTick"
                        :compact="true"
                        :stack-index="i + 1"
                        :tab-side="((i + 1) % 2 === 0) ? 'left' : 'right'"
                        :collapsed="!(hoveredDeckId === (lane.key + '|' + col.dayKey) && hoveredEntryId === String(element.id))"
                        :increment-minutes="incrementMinutes"
                        @start="startTimer"
                        @stop="stopTimer"
                        @save="saveCard"
                        @delete="c => deleteCard(lane, col, c)"
                      />
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </template>
        </div>
      </section>
    </div>
  </div>
</template>


<style scoped>
/* Weekly board scroller */
.board__scroller {
  margin-top: 6px;
  padding: 10px 10px 14px;
  background: var(--panel);
  border-radius: var(--radius);
  border: 1px solid var(--border);
  box-shadow: var(--shadow-sm);
  overflow: auto;
}

/* Spreadsheet-style weekly grid */
.grid {
  --rowhead-w: 182px;
  --grid-gap: 8px;
  --cell-min-h: 228px;

  display: grid;
  grid-template-columns: var(--rowhead-w) repeat(7, minmax(210px, 1fr));
  gap: var(--grid-gap);
  align-items: start;
  padding: 4px 0;
}

.cell {
  background: var(--panel);
  border: 1px solid var(--border);
  border-radius: var(--radius);

  /* tighter + predictable whitespace */
  min-height: var(--cell-min-h);
  position: relative;

  /* reserve a safe header band so stacked cards never cover the hours/+ controls */
  padding: 38px 8px 8px;

  overflow: visible;
  isolation: isolate;
}

/* Container for compact entries inside a cell (static deck, no drag) */
.cell .droplist {
  margin-top: 0px;
  position: relative;
  display: block;
  min-height: 0;
  padding: 0 8px 8px;
}

/* Deck wrapper (front card is in-flow; behind cards are absolutely stacked) */
.deck {
  position: relative;

  /* deck variables must live on a real element (scoped :root won't apply) */
  --deck-peek: 40px;
  --deck-step: 22px;

  /* Constant headroom policy (must match MAX_DECK_BEHIND in script) */
  --deck-peek-count: 3;

  /* Derived headroom so previous entries can peek ABOVE the front card without escaping the cell */
  --deck-headroom: calc((var(--deck-peek-count) * var(--deck-step)) + 8px);

  /* reserve space so older tabs can peek above the front card */
  padding-top: var(--deck-headroom);
}

.deckFront {
  position: relative;
  z-index: 120;
  transform: translateY(var(--deck-front-push, 0px));
  transition: transform 140ms ease;
}

.deckBehind {
  position: absolute;
  left: 0;
  right: 0;
  top: var(--deck-headroom); /* baseline aligns with the front card top */
  z-index: 100; /* below deckFront (120) by default */
  pointer-events: auto;
}

/* When hovering a behind-card in THIS deck, allow behind stack to render above front */
.deck.deck--hovering .deckBehind {
  z-index: 160;
}


/* Collapsed cards stacked ABOVE and BEHIND the front card */
.deckItem {
  position: absolute;
  left: 0;
  right: 0;
  max-width: 100%;

  /* i=1 should already be above the front card */
  top: calc(var(--deck-i) * var(--deck-step) * -1);

  z-index: calc(110 - var(--deck-i));

  height: var(--deck-peek);
  overflow: hidden;
  border-radius: 18px;
  transform: translateY(var(--deck-push, 0px));
  transition: transform 140ms ease, height 140ms ease;
}

/* Expand the active (currently hovered/selected) card.
   IMPORTANT: this is state-driven (deckItem--active) so the card stays expanded
   while the pointer moves within the deck (prevents the “empty gap” effect). */
.deckItem.deckItem--active {
  overflow: visible;
  z-index: 220;
  height: auto; /* allow the full folder card to render */
}

/* Optional: keep a hover affordance as well (same behavior) */
.deckItem:hover {
  overflow: visible;
  z-index: 220;
  height: auto;
}

/* When any item in a deck is expanded, keep its box visually above neighbors */
.deckItem { will-change: transform; }


.cell:hover {
  box-shadow: 0 0 0 1px color-mix(in srgb, var(--primary) 25%, transparent);
  border-color: color-mix(in srgb, var(--border) 60%, var(--primary) 40%);
}

.cell--head {
  background: transparent;
  border: none;
  min-height: auto;
  padding: 0;
}

/* Collapse top-left header spacer */
.grid > .cell.cell--head:first-child {
  padding: 0;
  min-height: 0;
  background: transparent;
  border: none;
  box-shadow: none;
}

/* Sticky project row headers */
.cell--rowhead {
  position: sticky;
  left: 0;
  z-index: 50;
  background: var(--panel);
  border-right: 1px solid var(--border);
  padding: 8px 6px 8px;
  overflow: visible; /* let meta editor expand */
}

.dayhead {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 5px 6px;
  border-bottom: 1px solid var(--border);
  color: var(--muted);
  font-weight: 600;
  font-size: 0.88rem;
  white-space: nowrap;
  gap: 6px;
}

.dayhead strong {
  letter-spacing: 0.01em;
  font-weight: 600;
}

.dayhead small {
  font-weight: 600;
  opacity: 0.9;
  font-size: 0.8rem;
  flex-shrink: 0;
}

/* Per-cell summary + add button */
.cell__sum {
  position: absolute;
  top: 4px;
  left: 6px;
  font-size: 0.78rem;
  font-weight: 600;
  color: var(--muted);
  padding: 0;
  background: transparent;
  border: none;

  /* ALWAYS above the deck */
  z-index: 500;
  pointer-events: none; /* click-through so only + is interactive */
}

.cell__actions {
  z-index: 500;
  pointer-events: auto;
  position: absolute;
  top: 6px;
  right: 6px;
  background: transparent;
}

/* Row-header project card */
.projcard {
  position: relative;
  display: flex;
  flex-direction: column;
  justify-content: space-between;
  gap: 6px;
  padding: 10px 10px 9px;
  border-radius: var(--radius);
  background: color-mix(in srgb, var(--panel-2) 92%, transparent);
  border: 1px solid color-mix(in srgb, var(--border) 85%, transparent);
  box-shadow: var(--shadow-md, 0 6px 16px rgba(0,0,0,.08));
  transition: box-shadow .15s ease, border-color .15s ease;
  overflow: visible;
}

.projcard:hover {
  box-shadow: var(--shadow-lg, 0 10px 28px rgba(0,0,0,.12));
  border-color: color-mix(in srgb, var(--border) 60%, var(--primary) 40%);
}


.projcard__head {
  display: flex;
  align-items: center;
  gap: 8px;
}

.projcard__head .title {
  margin: 0;
  font-size: 0.9rem;
  font-weight: 650;
  color: var(--text);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.projcard__running-icon {
  font-size: 0.9rem;
  flex-shrink: 0;
}

/* Project card hours row */
.projcard__hoursrow {
  display: flex;
  align-items: center;
  gap: 4px;
  margin-top: 2px;
  font-size: 0.78rem;
  color: var(--muted);
}

/* Make daily total hours plain text (no pill) */
.projcard__hours-pill {
  padding: 0;
  background: transparent;
  border: none;
  border-radius: 0;
  font-weight: 600;
  color: var(--muted);
}

/* Entry count text */
.projcard__entries {
  font-size: 0.75rem;
  color: var(--muted);
  white-space: nowrap;
  flex: 1;
  text-align: right;
  margin-right: 4px;
}

.projcard__foot {
  display: flex;
  align-items: center;
  margin-top: 4px;
}

.projcard__foot .spacer {
  flex: 1;
}

.projcard__foot .actions__icons {
  display: flex;
  gap: 6px;
}

.projcard__foot .mini.icon {
  background: var(--btn-blue-bg);
  border-color: var(--border);
}

.projcard__foot .mini.icon:hover {
  background: var(--btn-blue-bg-hover);
}

/* Priority dot (matches TimeCard) */
.prio-dot {
  width: 10px;
  height: 10px;
  border-radius: 999px;
  display: inline-block;
  border: 1px solid var(--border);
}

.prio-dot.p-low {
  background: #93c5fd;
  border-color: #93c5fd;
}
.prio-dot.p-normal {
  background: #86efac;
  border-color: #86efac; 
}
.prio-dot.p-high {
  background: #fdba74;
  border-color: #fdba74;
}
.prio-dot.p-critical {
  background: #fca5a5;
  border-color: #fca5a5;
}

/* Lane meta inline editor */
.lane-meta-editor {
  margin-top: 6px;
  padding: 6px 8px;
  border-radius: 10px;
  background: color-mix(in srgb, var(--panel-2) 85%, transparent);
  border: 1px solid color-mix(in srgb, var(--border) 85%, transparent);
  display: grid;
  gap: 4px;
  border-top: 1px dashed var(--border);
}

.lane-meta-editor--focus {
  margin: 4px 0 0;
}

.lane-meta-editor--row {
  margin-top: 6px;
}

.lane-meta-editor__field {
  display: grid;
  gap: 2px;
  font-size: 0.78rem;
  color: var(--muted);
}

.lane-meta-editor__field select,
.lane-meta-editor__field textarea {
  background: var(--panel);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 0.3rem 0.45rem;
  color: var(--text);
  font-size: 0.8rem;
}

.lane-meta-editor__actions {
  display: flex;
  justify-content: flex-end;
  gap: 4px;
  margin-top: 2px;
}

/* Fallback mini-button styling (in case global utilities are not being loaded) */
.mini {
  padding: 0.2rem 0.45rem;
  border: 1px solid var(--border);
  background: var(--btn-blue-bg);
  color: var(--primary);
  border-radius: 8px;
  cursor: pointer;
}

.mini:hover {
  background: var(--btn-blue-bg-hover);
}

.mini.icon {
  padding: 0.2rem;
  width: 28px;
  height: 28px;
  display: inline-grid;
  place-items: center;
  border-radius: 10px;
}

/* Folder-lane wrapper: the entire row reads as a single folder */
.laneRow {
  grid-column: 1 / -1;
  position: relative;

  /* tighter, consistent lane container */
  padding: 8px;
  border-radius: 18px;

  background: transparent;
  border: none;
  box-shadow: none;

  overflow: visible;
  transform: none; /* remove horizontal cascade shift to prevent collisions */
}

/* Visual folder chrome for the whole lane row */
.laneRow::before {
  content: "";
  position: absolute;
  left: 0;
  right: 0;
  top: 0;      /* IMPORTANT: no upward overlap; prevents lane collisions */
  bottom: 0;

  border-radius: 18px;

  /* stronger, more “concrete” lane border */
  border: 1px solid color-mix(in srgb, var(--border) 92%, transparent);
  background: color-mix(in srgb, var(--panel) 96%, transparent);
  box-shadow: var(--shadow-sm);

  z-index: 0;
}

/* lane content should always sit above the chrome */
.laneRow > * {
  position: relative;
  z-index: 1;
}



/* Inner grid aligns with the header columns */
.laneRow__grid {
  --rowhead-w: 182px;
  display: grid;
  grid-template-columns: var(--rowhead-w) repeat(7, minmax(210px, 1fr));
  gap: 8px;
  align-items: start;
}

/* Blend the rowhead cell into the lane folder */
.laneRow__grid .cell--rowhead {
  background: transparent;
  border: none;
  padding: 0;
  min-height: var(--cell-min-h);
}

/* Slightly soften day cell borders so the lane reads unified */
.laneRow__grid .cell {
  border-radius: 14px;
  border-color: color-mix(in srgb, var(--border) 78%, transparent);
}



.laneRow.prio-low::before {
  background: color-mix(in srgb, #93c5fd 14%, var(--panel));
  border-color: color-mix(in srgb, #93c5fd 22%, var(--border));
}
.laneRow.prio-normal::before {
  background: color-mix(in srgb, #86efac 12%, var(--panel));
  border-color: color-mix(in srgb, #86efac 18%, var(--border));
}
.laneRow.prio-high::before {
  background: color-mix(in srgb, #fdba74 12%, var(--panel));
  border-color: color-mix(in srgb, #fdba74 18%, var(--border));
}
.laneRow.prio-critical::before {
  background: color-mix(in srgb, #fca5a5 12%, var(--panel));
  border-color: color-mix(in srgb, #fca5a5 18%, var(--border));
}

</style>