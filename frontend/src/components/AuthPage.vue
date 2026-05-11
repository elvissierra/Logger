<script setup>
import { ref } from 'vue'
import { postJSON, getJSON } from '../lib/api'

const emit = defineEmits(['login-success'])

const view = ref('login')

const email = ref('')
const password = ref('')
const inviteCode = ref('')
const orgNamePreview = ref('')
const inviteCodeError = ref('')
const loading = ref(false)
const error = ref('')

async function handleLogin() {
  error.value = ''
  loading.value = true
  try {
    const user = await postJSON('/api/auth/login', { email: email.value, password: password.value })
    emit('login-success', user)
  } catch (e) {
    error.value = e.message || 'Something went wrong'
  } finally {
    loading.value = false
  }
}

async function handleRegister() {
  error.value = ''
  loading.value = true
  const body = { email: email.value, password: password.value }
  if (view.value === 'register-org') body.invite_code = inviteCode.value
  try {
    const user = await postJSON('/api/auth/register', body)
    emit('login-success', user)
  } catch (e) {
    error.value = e.message || 'Something went wrong'
  } finally {
    loading.value = false
  }
}

async function checkInviteCode() {
  inviteCodeError.value = ''
  orgNamePreview.value = ''
  const code = inviteCode.value.trim()
  if (!code) return
  try {
    const data = await getJSON(`/api/orgs/validate-code?code=${encodeURIComponent(code)}`)
    orgNamePreview.value = data.org_name
  } catch {
    inviteCodeError.value = 'Invalid invite code'
  }
}

function reset() {
  email.value = ''
  password.value = ''
  inviteCode.value = ''
  orgNamePreview.value = ''
  inviteCodeError.value = ''
  error.value = ''
}

function goLogin() { reset(); view.value = 'login' }
function goPickPath() { reset(); view.value = 'pick-path' }
function pickSolo() { view.value = 'register-solo' }
function pickOrg() { view.value = 'register-org' }
</script>

<template>
  <div class="auth">
    <div class="auth__card">

      <!-- LOGIN -->
      <template v-if="view === 'login'">
        <h1 class="auth__title">Welcome back</h1>
        <p class="auth__sub">Sign in to your account</p>
        <form @submit.prevent="handleLogin" class="auth__form">
          <input v-model="email" type="email" placeholder="Email" required class="auth__input" />
          <input v-model="password" type="password" placeholder="Password" required class="auth__input" />
          <p v-if="error" class="auth__error">{{ error }}</p>
          <button type="submit" class="auth__btn" :disabled="loading">
            {{ loading ? 'Signing in…' : 'Sign in' }}
          </button>
        </form>
        <p class="auth__switch">
          No account? <button class="auth__link" @click="goPickPath">Create one</button>
        </p>
      </template>

      <!-- PATH SELECTOR -->
      <template v-else-if="view === 'pick-path'">
        <h1 class="auth__title">Create an account</h1>
        <p class="auth__sub">How will you be using Logger?</p>
        <div class="auth__paths">
          <button class="auth__path-card" @click="pickSolo">
            <span class="auth__path-icon">👤</span>
            <strong>Solo user</strong>
            <span class="auth__path-desc">Personal time tracking, just for you</span>
          </button>
          <button class="auth__path-card" @click="pickOrg">
            <span class="auth__path-icon">🏢</span>
            <strong>Join an organization</strong>
            <span class="auth__path-desc">You have an invite code from your team</span>
          </button>
        </div>
        <p class="auth__switch">
          Already have an account? <button class="auth__link" @click="goLogin">Sign in</button>
        </p>
      </template>

      <!-- REGISTER SOLO -->
      <template v-else-if="view === 'register-solo'">
        <h1 class="auth__title">Create your account</h1>
        <p class="auth__sub">Personal time tracking</p>
        <form @submit.prevent="handleRegister" class="auth__form">
          <input v-model="email" type="email" placeholder="Email" required class="auth__input" />
          <input v-model="password" type="password" placeholder="Password (8+ chars)" minlength="8" required class="auth__input" />
          <p v-if="error" class="auth__error">{{ error }}</p>
          <button type="submit" class="auth__btn" :disabled="loading">
            {{ loading ? 'Creating account…' : 'Create account' }}
          </button>
        </form>
        <p class="auth__switch">
          <button class="auth__link" @click="goPickPath">← Back</button>
        </p>
      </template>

      <!-- REGISTER ORG MEMBER -->
      <template v-else-if="view === 'register-org'">
        <h1 class="auth__title">Join your organization</h1>
        <p class="auth__sub">Enter the invite code you were given</p>
        <form @submit.prevent="handleRegister" class="auth__form">
          <input
            v-model="inviteCode"
            type="text"
            placeholder="Invite code"
            required
            class="auth__input auth__input--code"
            @blur="checkInviteCode"
          />
          <p v-if="orgNamePreview" class="auth__org-preview">✓ {{ orgNamePreview }}</p>
          <p v-if="inviteCodeError" class="auth__error">{{ inviteCodeError }}</p>
          <input v-model="email" type="email" placeholder="Email" required class="auth__input" />
          <input v-model="password" type="password" placeholder="Password (8+ chars)" minlength="8" required class="auth__input" />
          <p v-if="error" class="auth__error">{{ error }}</p>
          <button type="submit" class="auth__btn" :disabled="loading || !!inviteCodeError">
            {{ loading ? 'Creating account…' : 'Create account' }}
          </button>
        </form>
        <p class="auth__switch">
          <button class="auth__link" @click="goPickPath">← Back</button>
        </p>
      </template>

    </div>
  </div>
</template>

<style scoped>
.auth {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--bg);
  padding: 24px;
}

.auth__card {
  background: var(--panel);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  box-shadow: var(--shadow-md);
  padding: 40px 36px;
  width: 100%;
  max-width: 440px;
}

.auth__title {
  font-size: 1.4rem;
  font-weight: 700;
  color: var(--text);
  margin: 0 0 4px;
}

.auth__sub {
  color: var(--muted);
  font-size: 0.9rem;
  margin: 0 0 24px;
}

.auth__form {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.auth__input {
  padding: 10px 14px;
  border: 1px solid var(--border);
  border-radius: 8px;
  background: var(--panel-2);
  color: var(--text);
  font-size: 0.95rem;
  font-family: inherit;
  outline: none;
  transition: border-color 0.15s;
}

.auth__input:focus {
  border-color: var(--primary);
}

.auth__input--code {
  width: 100%;
  letter-spacing: 0.05em;
  text-transform: uppercase;
}

.auth__org-preview {
  color: var(--primary);
  font-size: 0.85rem;
  margin: 0;
}

.auth__error {
  color: #d94f4f;
  font-size: 0.85rem;
  margin: 0;
}

.auth__btn {
  padding: 11px 20px;
  background: var(--primary);
  color: #fff;
  border: none;
  border-radius: 999px;
  font-size: 0.95rem;
  font-weight: 600;
  font-family: inherit;
  cursor: pointer;
  transition: background 0.15s;
}

.auth__btn:hover:not(:disabled) {
  background: var(--primary-600);
}

.auth__btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.auth__switch {
  margin-top: 20px;
  text-align: center;
  font-size: 0.875rem;
  color: var(--muted);
}

.auth__link {
  background: none;
  border: none;
  color: var(--primary);
  font-size: inherit;
  font-family: inherit;
  cursor: pointer;
  padding: 0;
  text-decoration: underline;
}

.auth__paths {
  display: flex;
  flex-direction: column;
  gap: 12px;
  margin-bottom: 8px;
}

.auth__path-card {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 4px;
  padding: 16px 20px;
  border: 1px solid var(--border);
  border-radius: var(--radius);
  background: var(--panel-2);
  cursor: pointer;
  text-align: left;
  font-family: inherit;
  transition: border-color 0.15s, background 0.15s;
}

.auth__path-card:hover {
  border-color: var(--primary);
  background: var(--btn-blue-bg);
}

.auth__path-icon {
  font-size: 1.4rem;
  margin-bottom: 4px;
}

.auth__path-card strong {
  color: var(--text);
  font-size: 0.95rem;
}

.auth__path-desc {
  color: var(--muted);
  font-size: 0.82rem;
}
</style>
