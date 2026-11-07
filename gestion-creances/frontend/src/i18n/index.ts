// Architecture de traduction : français par défaut ; l'arabe (RTL) et l'anglais
// s'ajoutent en complétant ar.ts / en.ts (les clés absentes retombent sur le français).
import i18n from "i18next";
import { initReactI18next } from "react-i18next";
import fr from "./fr";
import en from "./en";
import ar from "./ar";

export const LANGS = [
  { code: "fr", label: "Français", dir: "ltr" },
  { code: "ar", label: "العربية", dir: "rtl" },
  { code: "en", label: "English", dir: "ltr" },
] as const;

i18n.use(initReactI18next).init({
  resources: { fr: { translation: fr }, en: { translation: en }, ar: { translation: ar } },
  lng: localStorage.getItem("gpc_lang") || "fr",
  fallbackLng: "fr",
  interpolation: { escapeValue: false },
});

export default i18n;
