import { createApp } from 'vue'
import { createPinia } from 'pinia'
import { createAuth0 } from '@auth0/auth0-vue'
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
      redirect_uri: 'http://localhost:5173/callback',
      audience: 'https://api.hockey-blast-predictions.com',
      scope: 'openid profile email',
    },
    cacheLocation: 'localstorage',
  })
)

app.use(router)
app.mount('#app')
