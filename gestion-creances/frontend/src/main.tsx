import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import { MantineProvider, createTheme, DirectionProvider } from "@mantine/core";
import { DatesProvider } from "@mantine/dates";
import { Notifications } from "@mantine/notifications";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import "dayjs/locale/fr";
import "@mantine/core/styles.css";
import "@mantine/dates/styles.css";
import "@mantine/notifications/styles.css";
import "@mantine/charts/styles.css";
import "./i18n";
import "./styles.css";
import { AuthProvider } from "./auth";
import App from "./App";

const theme = createTheme({
  primaryColor: "brand",
  colors: {
    brand: ["#eef3f9", "#d9e3f0", "#b0c6e0", "#84a6cf", "#5f8bc1", "#4779b8", "#3a6fb5", "#2c5d9f", "#23528f", "#1f3a5f"],
  },
  fontFamily: "Inter, 'Segoe UI', Roboto, Arial, sans-serif",
  fontFamilyMonospace: "'JetBrains Mono', 'SFMono-Regular', Consolas, monospace",
  defaultRadius: "md",
  headings: { fontFamily: "Inter, 'Segoe UI', Roboto, Arial, sans-serif" },
});

const qc = new QueryClient({ defaultOptions: { queries: { staleTime: 20_000, retry: 1, refetchOnWindowFocus: false } } });

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <DirectionProvider>
      <MantineProvider theme={theme} defaultColorScheme="light">
        <DatesProvider settings={{ locale: "fr", firstDayOfWeek: 1 }}>
          <Notifications position="top-right" />
          <QueryClientProvider client={qc}>
            <BrowserRouter>
              <AuthProvider>
                <App />
              </AuthProvider>
            </BrowserRouter>
          </QueryClientProvider>
        </DatesProvider>
      </MantineProvider>
    </DirectionProvider>
  </React.StrictMode>
);
