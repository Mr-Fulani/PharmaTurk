import { domAnimation } from 'framer-motion'

// Фичи framer-motion для LazyMotion в шапке грузятся отдельным чанком после
// гидрации, а не в общем _app: шапка есть на каждой странице.
export default domAnimation
