/**
 * stk Framework - Central Configuration
 * Monochrome brutalist palette
 */

const config = {
    // Common Vue settings
    delimiters: ['${', '}'],

    // Vuetify configuration
    vuetifyConfig: {
        defaults: {
            VTextField: {
                variant: 'outlined'
            },
            VSelect: {
                variant: 'outlined'
            },
            VTextarea: {
                variant: 'outlined'
            },
            VCombobox: {
                variant: 'outlined'
            },
            VChip: {
                size: 'small',
                rounded: 'sm'
            },
            VCard: {
                elevation: 0,
                rounded: 0
            },
            VMenu: {
                offset: 10
            },
            VBtn: {
                variant: 'elevated',
                size: 'small',
                rounded: 0
            },
            VDialog: {
                rounded: 0
            },
            VToolbar: {
                elevation: 0
            },
            VDataTableServer: {
                itemsPerPage: 25,
                itemsPerPageOptions: [25, 50, 100]
            }
        },
        theme: {
            defaultTheme: window.__settings__?.dark ? 'dark' : 'light',
            themes: {
                light: {
                    dark: false,
                    colors: {
                        primary: '#1a1a1a',
                        secondary: '#555555',
                        accent: '#333333',
                        error: '#b91c1c',
                        info: '#1a1a1a',
                        success: '#166534',
                        warning: '#a16207',
                        background: '#fafafa',
                        surface: '#fafafa',
                        'surface-light': '#f0f0f0',
                        'on-surface': '#1a1a1a',
                    }
                },
                dark: {
                    dark: true,
                    colors: {
                        primary: '#e5e5e5',
                        secondary: '#a3a3a3',
                        accent: '#d4d4d4',
                        error: '#fca5a5',
                        info: '#e5e5e5',
                        success: '#86efac',
                        warning: '#fde047',
                        background: '#0a0a0a',
                        surface: '#141414',
                        'surface-light': '#262626',
                        'on-surface': '#e5e5e5',
                    }
                }
            }
        }
    }
};
