<script setup>
import { ref } from 'vue'
import { postJSON } from '../lib/api'

const email = ref('')
const password = ref('')
const loading = ref(false)
const error = ref(null)

// mode: 'login' (default) or 'register'
const mode = ref('login')

const emit = defineEmits(['login-success'])

async function handleSubmit () {
  error.value = null
  loading.value = true
  try {
    const path = mode.value === 'register' ? '/api/auth/register' : '/api/auth/login'
    const me = await postJSON(path, {
      email: email.value,
      password: password.value
    })
    // Both login and register return UserOut and set cookies,
    // so treat both as "logged in" from the app's perspective.
    emit('login-success', me)
  } catch (e) {
    let msg =
      mode.value === 'register'
        ? 'Registration failed. Please check your details and try again.'
        : 'Login failed. Check your email and password.'
    const raw = String(e.message || '')
    // best-effort parse of JSON error from backend (FastAPI-style {"detail": "..."} )
    try {
      const parsed = JSON.parse(raw)
      if (parsed && parsed.detail) {
        msg = parsed.detail
      }
    } catch (_) {}
    error.value = msg
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="login">
    <div class="login__card">
        <h2 class="login__title">
          {{ mode === 'register' ? 'Create a Logger account' : 'Sign in to Logger' }}
        </h2>
        <p class="login__subtitle">
          <span v-if="mode === 'register'">
            Create an account to start planning your week and tracking time.
          </span>
          <span v-else>
            Plan your week, track your time, and keep projects aligned.
          </span>
        </p>

      <form class="login__form" @submit.prevent="handleSubmit">
        <label class="login__field">
          <span class="login__label">Email</span>
          <input
            v-model="email"
            type="email"
            autocomplete="email"
            required
            class="login__input"
          >
        </label>

        <label class="login__field">
          <span class="login__label">Password</span>
          <input
            v-model="password"
            type="password"
            autocomplete="current-password"
            required
            class="login__input"
          >
        </label>

        <p v-if="error" class="login__error">
          {{ error }}
        </p>

        <button
          type="submit"
          class="login__submit"
          :disabled="loading"
        >
          <span v-if="!loading">
            {{ mode === 'register' ? 'Create account' : 'Sign in' }}
          </span>
          <span v-else>
            {{ mode === 'register' ? 'Creating…' : 'Signing in…' }}
          </span>
        </button>
        <div class="login__switch">
          <button
            type="button"
            class="login__link"
            @click="mode = mode === 'register' ? 'login' : 'register'"
          >
            <span v-if="mode === 'register'">
              Already have an account? Sign in
            </span>
            <span v-else>
              Need an account? Create one
            </span>
          </button>
        </div>
      </form>
    </div>
  </div>
</template>

<style scoped>
.login {
  min-height: calc(100vh - 64px);
  display: flex;
  align-items: center;
  justify-content: center;
}

.login__card {
  width: 100%;
  max-width: 420px;
  padding: 24px 24px 28px;
  background: var(--panel);
  border-radius: var(--radius);
  box-shadow: var(--shadow-md);
  border: 1px solid var(--border);
}

.login__title {
  margin: 0 0 4px;
  font-size: 1.35rem;
  font-weight: 700;
}

.login__subtitle {
  margin: 0 0 18px;
  font-size: 0.9rem;
  color: var(--muted);
}

.login__form {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.login__field {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.login__label {
  font-size: 0.8rem;
  font-weight: 600;
  color: var(--muted);
}

.login__input {
  border-radius: 8px;
  border: 1px solid var(--border);
  padding: 8px 10px;
  font-size: 0.9rem;
  background: var(--panel-2);
  color: var(--text);
}

.login__input:focus {
  outline: none;
  border-color: var(--primary);
  box-shadow: 0 0 0 1px color-mix(in srgb, var(--primary) 40%, transparent);
}

.login__error {
  margin: 2px 0 0;
  font-size: 0.8rem;
  color: #b91c1c;
}

.login__submit {
  margin-top: 4px;
  border: none;
  border-radius: 999px;
  padding: 0.6rem 1.1rem;
  font-size: 0.9rem;
  font-weight: 600;
  cursor: pointer;
  background: var(--primary);
  color: white;
  box-shadow: var(--shadow-sm);
  transition: background 0.15s ease, transform 0.06s ease, box-shadow 0.15s ease;
}

.login__submit:disabled {
  opacity: 0.7;
  cursor: default;
}

.login__submit:not(:disabled):hover {
  background: var(--primary-600);
  transform: translateY(1px);
}

.login__switch {
  margin-top: 10px;
  text-align: center;
}

.login__link {
  border: none;
  background: none;
  color: var(--primary);
  font-size: 0.8rem;
  cursor: pointer;
  padding: 0;
}

.login__link:hover {
  text-decoration: underline;
}
</style>