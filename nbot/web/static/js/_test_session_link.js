nbotVueApp.component('session-link', {
            props: {
                value: { type: String, default: '' },
                inline: { type: Boolean, default: false },
                prefix: { type: String, default: '' },
                showIcon: { type: Boolean, default: true },
                stopPropagation: { type: Boolean, default: true },
            },
            computed: {
                _app() {
                    return window.__nbotVueApp || null;
                },
                hasSession() {
                    if (!this.value) return false;
                    const app = this._app;
                    if (!app || !Array.isArray(app.sessions)) return false;
                    return app.sessions.some(s => s && s.id === this.value);
                },
                titleText() {
                    return this.hasSession
                        ? '????????'
                        : '???????????';
                },
                linkClass() {
                    return [
                        'memfs-session-link',
                        this.inline ? 'memfs-session-link-inline' : '',
                        { 'memfs-session-link-disabled': !this.hasSession },
                    ];
                },
            },
            methods: {
                async handleClick(e) {
                    e.preventDefault();
                    if (this.stopPropagation) {
                        e.stopPropagation();
                    }
                    if (!this.hasSession) {
                        const app = this._app;
                        if (app && typeof app.showToast === 'function') {
                            app.showToast('???????????', 'warning');
                        }
                        return;
                    }
                    const app = this._app;
                    const session = app && Array.isArray(app.sessions)
                        ? app.sessions.find(s => s && s.id === this.value)
                        : null;
                    if (!session) return;
                    try {
                        await app.openSession(session);
                    } catch (err) {
                        console.error('[session-link] failed to open session', this.value, err);
                        if (typeof app.showToast === 'function') {
                            app.showToast('??????', 'error');
                        }
                    }
                },
            },
            template: `
                <a href="#"
                   :class="linkClass"
                   :title="titleText"
                   @click="handleClick">
                    <template v-if="prefix">{{ prefix }}</template>{{ value }}<i v-if="showIcon && !inline" class="fas fa-external-link-alt memfs-session-link-icon"></i>
                </a>
            `,
       
