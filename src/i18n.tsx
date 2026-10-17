import type {} from "@decky/ui";
import {
  createContext,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from "react";
import { resolveLanguage, translate } from "./localization";
export { resolveLanguage, translate } from "./localization";

const LanguageContext = createContext("en");
export function LanguageProvider({ children }: { children: ReactNode }) {
  const [language, setLanguage] = useState("en");
  useEffect(() => {
    let mounted = true;
    const update = () => {
      void SteamClient.Settings.GetCurrentLanguage()
        .then((value) => {
          if (mounted) setLanguage(resolveLanguage(value));
        })
        .catch(() => {});
    };
    update();
    const listener = SteamClient.Settings.RegisterForSettingsChanges?.(() =>
      update(),
    );
    return () => {
      mounted = false;
      listener?.unregister();
    };
  }, []);
  return (
    <LanguageContext.Provider value={language}>
      {children}
    </LanguageContext.Provider>
  );
}
export function useT() {
  const language = useContext(LanguageContext);
  return (key: string) => translate(language, key);
}
