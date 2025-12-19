
<script setup>
import draggable from 'vuedraggable'
import TimeCard from './TimeCard.vue'

const props = defineProps({
  // container state
  layoutMode: { type: String, required: true },
  headerDays: { type: Array, required: true },
  swimlanes: { type: Array, required: true },

  // timer + ticking
  runningId: { required: true },
  nowTick: { required: true },

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
                  🌀
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

              <draggable
                v-if="col.cards.length"
                v-model="col.cards"
                item-key="id"
                :animation="160"
                handle=".handle"
                class="droplist"
                :group="{ name: 'cards', pull: true, put: true }"
                ghost-class="drag-ghost"
                chosen-class="drag-chosen"
                drag-class="drag-dragging"
                @change="onCellChange(lane, col, $event)"
                @end="onReorderCell(lane, col.dayKey)"
              >
                <template #item="{ element, index }">
                  <TimeCard
                    :card="element"
                    :open-on-mount="element.__new === true"
                    :running-id="runningId"
                    :now-tick="nowTick"
                    :compact="true"
                    :tab-side="(index % 2 === 0) ? 'left' : 'right'"
                    @start="startTimer"
                    @stop="stopTimer"
                    @save="saveCard"
                    @delete="c => deleteCard(lane, col, c)"
                  />
                </template>
              </draggable>
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
  --rowhead-w: 190px;
  display: grid;
  grid-template-columns: var(--rowhead-w) repeat(7, minmax(220px, 1fr));
  gap: 10px;
  align-items: start;
  padding: 6px 0;
}

.cell {
  background: var(--panel);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  min-height: 320px;
  position: relative;
  padding: 26px 6px 10px;
  overflow: visible;
  isolation: isolate;
}

/* Container for compact entries inside a cell (simple list for now) */
.cell .droplist {
  margin-top: 8px;
  display: grid;
  gap: 8px;
  min-height: 0;
  padding: 0 6px 8px;
}


.cell:hover {
  box-shadow: 0 0 0 1px color-mix(in srgb, var(--primary) 25%, transparent);
  border-color: color-mix(in srgb, var(--border) 60%, var(--primary) 40%);
}

.cell--head {
  background: transparent;
  border: none;
  min-height: auto;
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
  padding: 6px 6px;
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
}

.cell__actions {
  position: absolute;
  top: 6px;
  right: 6px;
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
  box-shadow: var(--shadow-sm);
  overflow: visible;
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
  padding: 12px 10px 12px;
  border-radius: 18px;
  border: 1px solid color-mix(in srgb, var(--border) 70%, transparent);
  background: color-mix(in srgb, var(--panel) 92%, transparent);
  box-shadow: var(--shadow-sm);
  overflow: visible;
  transform: translateX(var(--lane-x, 0px));
}

/* Deck overlap: lanes slightly tuck into each other */
.laneRow + .laneRow {
  margin-top: -14px;
}


/* Inner grid aligns with the header columns */
.laneRow__grid {
  --rowhead-w: 190px;
  display: grid;
  grid-template-columns: var(--rowhead-w) repeat(7, minmax(220px, 1fr));
  gap: 10px;
  align-items: start;
}

/* Blend the rowhead cell into the lane folder */
.laneRow__grid .cell--rowhead {
  background: transparent;
  border: none;
  padding: 0;
}

/* Slightly soften day cell borders so the lane reads unified */
.laneRow__grid .cell {
  border-radius: 14px;
  border-color: color-mix(in srgb, var(--border) 78%, transparent);
}

/* Deck cascade offsets + z-order (first lane stays on top) */
.grid > section.laneRow:nth-of-type(1) { z-index: 20; --lane-x: 0px; }
.grid > section.laneRow:nth-of-type(2) { z-index: 19; --lane-x: 8px; }
.grid > section.laneRow:nth-of-type(3) { z-index: 18; --lane-x: 16px; }
.grid > section.laneRow:nth-of-type(4) { z-index: 17; --lane-x: 24px; }
.grid > section.laneRow:nth-of-type(5) { z-index: 16; --lane-x: 32px; }
.grid > section.laneRow:nth-of-type(6) { z-index: 15; --lane-x: 40px; }
.grid > section.laneRow:nth-of-type(7) { z-index: 14; --lane-x: 48px; }
.grid > section.laneRow:nth-of-type(8) { z-index: 13; --lane-x: 56px; }
.grid > section.laneRow:nth-of-type(9) { z-index: 12; --lane-x: 64px; }
.grid > section.laneRow:nth-of-type(10) { z-index: 11; --lane-x: 72px; }


.laneRow.prio-low { background: color-mix(in srgb, #93c5fd 14%, var(--panel)); border-color: color-mix(in srgb, #93c5fd 22%, var(--border)); }
.laneRow.prio-normal { background: color-mix(in srgb, #86efac 12%, var(--panel)); border-color: color-mix(in srgb, #86efac 18%, var(--border)); }
.laneRow.prio-high { background: color-mix(in srgb, #fdba74 12%, var(--panel)); border-color: color-mix(in srgb, #fdba74 18%, var(--border)); }
.laneRow.prio-critical { background: color-mix(in srgb, #fca5a5 12%, var(--panel)); border-color: color-mix(in srgb, #fca5a5 18%, var(--border)); }
</style>