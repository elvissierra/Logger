<script setup>
import { ref, onMounted, computed } from 'vue'
import { postJSON, getJSON, patchJSON } from '../lib/api'

const props = defineProps({
  user: { type: Object, required: true },
})

const emit = defineEmits(['org-created', 'back'])

const orgName = ref('')
const address = ref('')
const phone = ref('')
const headcount = ref('')
const createError = ref('')
const createLoading = ref(false)

const org = ref(null)
const members = ref([])
const loadError = ref('')
const copied = ref(false)

const editing = ref(false)
const editName = ref('')
const editAddress = ref('')
const editPhone = ref('')
const editHeadcount = ref('')
const editError = ref('')
const editLoading = ref(false)

const isManaging = computed(() => !!props.user.org_id)

onMounted(async () => {
  if (isManaging.value) await loadOrg()
})

async function loadOrg() {
  try {
    const [orgData, membersData] = await Promise.all([
      getJSON('/api/orgs/me'),
      props.user.is_org_admin ? getJSON('/api/orgs/members') : Promise.resolve([]),
    ])
    org.value = orgData
    members.value = membersData
  } catch {
    loadError.value = 'Failed to load organization data'
  }
}

async function handleCreateOrg() {
  createError.value = ''
  createLoading.value = true
  try {
    await postJSON('/api/orgs/', {
      name: orgName.value,
      address: address.value,
      phone: phone.value,
      headcount: parseInt(headcount.value, 10),
    })
    emit('org-created')
  } catch {
    createError.value = 'Failed to create organization'
  } finally {
    createLoading.value = false
  }
}

function startEdit() {
  editName.value = org.value.name
  editAddress.value = org.value.address
  editPhone.value = org.value.phone
  editHeadcount.value = org.value.headcount
  editing.value = true
}

function cancelEdit() {
  editing.value = false
  editError.value = ''
}

async function saveEdit() {
  editError.value = ''
  editLoading.value = true
  try {
    org.value = await patchJSON('/api/orgs/', {
      name: editName.value,
      address: editAddress.value,
      phone: editPhone.value,
      headcount: parseInt(editHeadcount.value, 10),
    })
    editing.value = false
  } catch {
    editError.value = 'Failed to save changes'
  } finally {
    editLoading.value = false
  }
}

async function copyInviteCode() {
  await navigator.clipboard.writeText(org.value.invite_code)
  copied.value = true
  setTimeout(() => { copied.value = false }, 2000)
}
</script>

<template>
  <div class="orgpanel">
    <div class="orgpanel__inner">

      <!-- CREATE ORG FORM -->
      <template v-if="!isManaging">
        <div class="orgpanel__header">
          <h2 class="orgpanel__title">Create your organization</h2>
          <p class="orgpanel__sub">Set up your team's workspace. You'll become the admin and get an invite code to share with your team.</p>
        </div>
        <form @submit.prevent="handleCreateOrg" class="orgpanel__form">
          <label class="orgpanel__label">Organization name
            <input v-model="orgName" type="text" required class="orgpanel__input" placeholder="Acme Corp" />
          </label>
          <label class="orgpanel__label">Address
            <input v-model="address" type="text" required class="orgpanel__input" placeholder="123 Main St, City, State" />
          </label>
          <label class="orgpanel__label">Phone number
            <input v-model="phone" type="text" required class="orgpanel__input" placeholder="(555) 000-0000" />
          </label>
          <label class="orgpanel__label">Headcount
            <input v-model="headcount" type="number" min="1" required class="orgpanel__input" placeholder="Number of employees" />
          </label>
          <p v-if="createError" class="orgpanel__error">{{ createError }}</p>
          <button type="submit" class="orgpanel__btn" :disabled="createLoading">
            {{ createLoading ? 'Creating…' : 'Create organization' }}
          </button>
        </form>
        <p class="orgpanel__back">
          <button class="orgpanel__link" @click="emit('back')">← Back to time tracker</button>
        </p>
      </template>

      <!-- MANAGE ORG -->
      <template v-else>
        <p v-if="loadError" class="orgpanel__error">{{ loadError }}</p>

        <template v-if="org">
          <div class="orgpanel__header">
            <div class="orgpanel__header-row">
              <h2 class="orgpanel__title">{{ org.name }}</h2>
              <button v-if="user.is_org_admin && !editing" class="mini" @click="startEdit">Edit</button>
            </div>
            <p class="orgpanel__sub">Organization dashboard</p>
          </div>

          <template v-if="editing">
            <form @submit.prevent="saveEdit" class="orgpanel__form">
              <label class="orgpanel__label">Name
                <input v-model="editName" type="text" required class="orgpanel__input" />
              </label>
              <label class="orgpanel__label">Address
                <input v-model="editAddress" type="text" required class="orgpanel__input" />
              </label>
              <label class="orgpanel__label">Phone
                <input v-model="editPhone" type="text" required class="orgpanel__input" />
              </label>
              <label class="orgpanel__label">Headcount
                <input v-model="editHeadcount" type="number" min="1" required class="orgpanel__input" />
              </label>
              <p v-if="editError" class="orgpanel__error">{{ editError }}</p>
              <div class="orgpanel__edit-actions">
                <button type="submit" class="orgpanel__btn" :disabled="editLoading">
                  {{ editLoading ? 'Saving…' : 'Save changes' }}
                </button>
                <button type="button" class="mini" @click="cancelEdit">Cancel</button>
              </div>
            </form>
          </template>

          <template v-else>
            <div class="orgpanel__info">
              <div class="orgpanel__info-row"><span class="orgpanel__info-label">Address</span><span>{{ org.address }}</span></div>
              <div class="orgpanel__info-row"><span class="orgpanel__info-label">Phone</span><span>{{ org.phone }}</span></div>
              <div class="orgpanel__info-row"><span class="orgpanel__info-label">Headcount</span><span>{{ org.headcount }}</span></div>
            </div>

            <div v-if="user.is_org_admin" class="orgpanel__invite">
              <p class="orgpanel__label">Team invite code</p>
              <div class="orgpanel__code-row">
                <code class="orgpanel__code">{{ org.invite_code }}</code>
                <button class="mini" @click="copyInviteCode">{{ copied ? '✓ Copied' : 'Copy' }}</button>
              </div>
              <p class="orgpanel__code-hint">Share this code verbally with team members so they can register.</p>
            </div>

            <div v-if="user.is_org_admin" class="orgpanel__members">
              <h3 class="orgpanel__section-title">Members ({{ members.length }})</h3>
              <div class="orgpanel__member-list">
                <div v-for="m in members" :key="m.id" class="orgpanel__member">
                  <span class="orgpanel__member-email">{{ m.email }}</span>
                  <span class="orgpanel__member-badge" :class="m.is_org_admin ? 'badge--admin' : 'badge--member'">
                    {{ m.is_org_admin ? 'Admin' : 'Member' }}
                  </span>
                </div>
              </div>
            </div>
          </template>
        </template>

        <p class="orgpanel__back">
          <button class="orgpanel__link" @click="emit('back')">← Back to time tracker</button>
        </p>
      </template>

    </div>
  </div>
</template>

<style scoped>
.orgpanel {
  min-height: 100vh;
  background: var(--bg);
  padding: 40px 24px;
}

.orgpanel__inner {
  max-width: 600px;
  margin: 0 auto;
}

.orgpanel__header { margin-bottom: 28px; }

.orgpanel__header-row {
  display: flex;
  align-items: center;
  gap: 12px;
}

.orgpanel__title {
  font-size: 1.5rem;
  font-weight: 700;
  color: var(--text);
  margin: 0 0 4px;
}

.orgpanel__sub {
  color: var(--muted);
  font-size: 0.9rem;
  margin: 0;
}

.orgpanel__form {
  display: flex;
  flex-direction: column;
  gap: 16px;
  background: var(--panel);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 28px;
  margin-bottom: 16px;
}

.orgpanel__label {
  display: flex;
  flex-direction: column;
  gap: 6px;
  font-size: 0.875rem;
  color: var(--muted);
  font-weight: 500;
}

.orgpanel__input {
  padding: 9px 13px;
  border: 1px solid var(--border);
  border-radius: 8px;
  background: var(--panel-2);
  color: var(--text);
  font-size: 0.95rem;
  font-family: inherit;
  outline: none;
  transition: border-color 0.15s;
}

.orgpanel__input:focus { border-color: var(--primary); }

.orgpanel__btn {
  align-self: flex-start;
  padding: 10px 24px;
  background: var(--primary);
  color: #fff;
  border: none;
  border-radius: 999px;
  font-size: 0.9rem;
  font-weight: 600;
  font-family: inherit;
  cursor: pointer;
  transition: background 0.15s;
}

.orgpanel__btn:hover:not(:disabled) { background: var(--primary-600); }
.orgpanel__btn:disabled { opacity: 0.6; cursor: not-allowed; }

.orgpanel__edit-actions {
  display: flex;
  align-items: center;
  gap: 12px;
}

.orgpanel__error {
  color: #d94f4f;
  font-size: 0.85rem;
  margin: 0;
}

.orgpanel__info {
  background: var(--panel);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 20px 24px;
  margin-bottom: 20px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.orgpanel__info-row {
  display: flex;
  justify-content: space-between;
  font-size: 0.9rem;
  color: var(--text);
}

.orgpanel__info-label {
  color: var(--muted);
  font-weight: 500;
}

.orgpanel__invite {
  background: var(--panel);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 20px 24px;
  margin-bottom: 20px;
}

.orgpanel__code-row {
  display: flex;
  align-items: center;
  gap: 12px;
  margin: 8px 0;
}

.orgpanel__code {
  font-family: monospace;
  font-size: 1rem;
  letter-spacing: 0.1em;
  color: var(--primary);
  background: var(--panel-2);
  border: 1px solid var(--border);
  border-radius: 6px;
  padding: 6px 12px;
}

.orgpanel__code-hint {
  color: var(--muted);
  font-size: 0.8rem;
  margin: 0;
}

.orgpanel__members {
  background: var(--panel);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 20px 24px;
  margin-bottom: 20px;
}

.orgpanel__section-title {
  font-size: 0.9rem;
  font-weight: 600;
  color: var(--muted);
  text-transform: uppercase;
  letter-spacing: 0.05em;
  margin: 0 0 16px;
}

.orgpanel__member-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.orgpanel__member {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-size: 0.9rem;
  color: var(--text);
}

.orgpanel__member-email { color: var(--text); }

.orgpanel__member-badge {
  font-size: 0.75rem;
  font-weight: 600;
  padding: 2px 8px;
  border-radius: 999px;
}

.badge--admin { background: var(--btn-blue-bg); color: var(--primary); }
.badge--member { background: var(--panel-2); color: var(--muted); }

.orgpanel__back { margin-top: 8px; }

.orgpanel__link {
  background: none;
  border: none;
  color: var(--primary);
  font-size: 0.875rem;
  font-family: inherit;
  cursor: pointer;
  padding: 0;
  text-decoration: underline;
}
</style>
