/**
 * stk Framework - Central Configuration
 * Monochrome brutalist palette
 */

const config = {
    // Common Vue settings
    delimiters: ['${', '}'],

    // Vuetify configuration
    vuetifyConfig: {
        // Tabler icon set for Vuetify's internal component icons (data-table
        // sort/pagination, select dropdown, checkboxes, alerts). Without this
        // Vuetify defaults to mdi aliases, which render blank since we ship no
        // MDI font. Pass-through any explicit "ti ti-*" string; prefix bare names.
        icons: {
            defaultSet: 'tabler',
            sets: {
                tabler: {
                    component: (props) => {
                        const icon = props.icon || '';
                        const cls = (icon.startsWith('ti ') || icon.startsWith('ti-'))
                            ? icon
                            : `ti ti-${icon}`;
                        return Vue.h(props.tag, { class: cls });
                    }
                }
            },
            aliases: {
                complete: 'check',
                cancel: 'circle-x',
                close: 'x',
                delete: 'x',
                clear: 'circle-x',
                success: 'circle-check',
                info: 'info-circle',
                warning: 'alert-triangle',
                error: 'alert-circle',
                prev: 'chevron-left',
                next: 'chevron-right',
                checkboxOn: 'square-check',
                checkboxOff: 'square',
                checkboxIndeterminate: 'square-minus',
                delimiter: 'circle',
                sortAsc: 'arrow-up',
                sortDesc: 'arrow-down',
                expand: 'chevron-down',
                menu: 'menu-2',
                subgroup: 'chevron-down',
                dropdown: 'chevron-down',
                radioOn: 'circle-check',
                radioOff: 'circle',
                edit: 'pencil',
                ratingEmpty: 'star',
                ratingFull: 'star-filled',
                ratingHalf: 'star-half-filled',
                loading: 'loader-2',
                first: 'chevrons-left',
                last: 'chevrons-right',
                unfold: 'arrows-sort',
                file: 'paperclip',
                plus: 'plus',
                minus: 'minus',
                calendar: 'calendar',
                treeviewCollapse: 'chevron-down',
                treeviewExpand: 'chevron-right',
                eyeDropper: 'color-picker',
                upload: 'upload',
                color: 'palette'
            }
        },
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
