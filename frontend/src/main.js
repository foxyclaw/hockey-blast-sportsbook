import { createApp } from 'vue'
import { createPinia } from 'pinia'
import { createAuth0 } from '@auth0/auth0-vue'
import router from './router'
import App from './App.vue'
import router from './router'
import './style.css'

const app = createApp(App)

app.use(createPinia())

app.use(
  createAuth0({
    domain: 'dev-tqe4zxubkkg82828.us.auth0.com',
    clientId: 'qhV0rAn6CywncUVjR3tjOCc45qaeBpj3',
    authorizationParams: {
      redirect_uri: `${window.location.origin}/callback`,
      scope: 'openid profile email',
    },
    cacheLocation: 'localstorage',
    cookieDomain: '.hockey-blast.com',
    onRedirectCallback: (appState) => {
      router.replace(appState?.returnTo || '/')
    },
  })
)

app.config.globalProperties.window = window

app.config.errorHandler = (err, instance, info) => {
  console.error('[Vue error]', err, info)
}

app.use(router)
app.mount('#app')
