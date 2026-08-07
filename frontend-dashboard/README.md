# DigiSpace Dashboard – Frontend Developer Task

This project is an implementation of the PulseGrid analytics dashboard based on the provided static design.

The objective was to build a pixel-perfect desktop dashboard using React and TypeScript while maintaining component modularity and clean architecture.

---

## 📐 Resolution

- **Target design resolution:** 1440 × 810 (Desktop)
- The page is intentionally non-responsive as per instructions.
- Layout is optimized specifically for the above resolution.

---

## 🚀 Tech Stack

- **React 19**
- **TypeScript**
- **Vite**
- **Apache ECharts (echarts-for-react)**
- **Redux Toolkit** (State management)
- **Custom CSS (Pixel-focused styling)**

---

## 🧩 Architecture & Implementation

- Each dashboard card (Lights, Water, Carbon, Energy, Footfall) is implemented as an **independent reusable component**.
- Charts are rendered using **Apache ECharts**.
- Global state management handled via **Redux Toolkit**.
- Strict TypeScript typing applied for components and state.
- Clean and modular folder structure.

---

## ✨ Extra Credit Implementation

### ✅ Adaptive Layout
The dashboard layout automatically reorganizes based on the number of rendered cards.
If cards are removed from the state, the grid adjusts dynamically without leaving empty spaces.
This is implemented using CSS Grid.

### ✅ TypeScript
All components and state logic are strictly typed.

### ✅ State Management
Redux Toolkit is used to manage dashboard state.

### ✅ Tests
Basic unit tests implemented using Jest and React Testing Library.

### ✅ Hosted Application
The application is deployed on Vercel.

Live Demo:
https://frontend-developer-task-cyan.vercel.app/

---

## 📂 Project Structure

