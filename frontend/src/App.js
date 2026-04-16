import "./App.css";
import { BrowserRouter, Route, Routes } from "react-router-dom";

import LoginPage from "./features/auth/LoginPage";
import AuctionRoomPage from "./features/auctions/AuctionRoomPage";
import OwnerDashboard from "./features/dashboard/OwnerDashboard";
import SubscriberDashboard from "./features/dashboard/SubscriberDashboard";
import ExternalChitsPage from "./features/external-chits/ExternalChitsPage";

function App() {
  return (
    <BrowserRouter future={{ v7_relativeSplatPath: true, v7_startTransition: true }}>
      <Routes>
        <Route path="/" element={<LoginPage />} />
        <Route path="/owner" element={<OwnerDashboard />} />
        <Route path="/subscriber" element={<SubscriberDashboard />} />
        <Route path="/auctions/:sessionId" element={<AuctionRoomPage />} />
        <Route path="/external-chits" element={<ExternalChitsPage />} />
      </Routes>
    </BrowserRouter>
  );
}

export default App;
