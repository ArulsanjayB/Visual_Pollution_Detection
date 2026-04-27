import React from 'react';
import { NavigationContainer } from '@react-navigation/native';
import { createNativeStackNavigator } from '@react-navigation/native-stack';
import { createBottomTabNavigator } from '@react-navigation/bottom-tabs';
import { Ionicons } from '@expo/vector-icons';
import { View, ActivityIndicator } from 'react-native';
import { useAuth } from '../context/AuthContext';

// Screens
import LoginScreen     from '../screens/auth/LoginScreen';

import CitizenHome         from '../screens/citizen/HomeScreen';
import SubmitReport        from '../screens/citizen/ReportScreen';
import CitizenHistory      from '../screens/citizen/HistoryScreen';
import CitizenReportDetail from '../screens/citizen/ReportDetailScreen';

import MunicipalDashboard from '../screens/municipal/DashboardScreen';
import MunicipalDetail    from '../screens/municipal/ReportDetailScreen';

import AdminScreen from '../screens/admin/AdminScreen';

const Stack = createNativeStackNavigator();
const Tab   = createBottomTabNavigator();

// ── Tab navigators ──────────────────────────────────────────────────────────

function CitizenTabs() {
  return (
    <Tab.Navigator screenOptions={tabOptions}>
      <Tab.Screen name="Home"    component={CitizenHome}    options={tabIcon('home')}  />
      <Tab.Screen name="Report"  component={SubmitReport}   options={tabIcon('camera')}/>
      <Tab.Screen name="History" component={CitizenHistory} options={tabIcon('list')}  />
    </Tab.Navigator>
  );
}

function MunicipalTabs() {
  return (
    <Tab.Navigator screenOptions={tabOptions}>
      <Tab.Screen name="Dashboard" component={MunicipalDashboard} options={tabIcon('stats-chart')} />
      <Tab.Screen name="Reports"   component={MunicipalDashboard} options={tabIcon('documents')}   />
    </Tab.Navigator>
  );
}

// ── Root navigator ────────────────────────────────────────────────────────────

export default function AppNavigator() {
  const { user, loading, role } = useAuth();

  if (loading) {
    return (
      <View style={{ flex: 1, justifyContent: 'center', alignItems: 'center' }}>
        <ActivityIndicator size="large" color="#1a237e" />
      </View>
    );
  }

  return (
    <NavigationContainer>
      <Stack.Navigator screenOptions={{ headerShown: false }}>
        {!user ? (
          // ── Auth stack ─────────────────────────────────────────────
          <Stack.Screen name="Login" component={LoginScreen} />
        ) : role === 'admin' ? (
          // ── Admin ─────────────────────────────────────────────────
          <Stack.Screen name="Admin" component={AdminScreen} />
        ) : role === 'municipal' ? (
          // ── Municipal ─────────────────────────────────────────────
          <>
            <Stack.Screen name="MunicipalTabs"   component={MunicipalTabs}     />
            <Stack.Screen name="MunicipalDetail" component={MunicipalDetail}
              options={{ headerShown: true, title: 'Report Detail' }} />
          </>
        ) : (
          // ── Citizen (default) ─────────────────────────────────────
          <>
            <Stack.Screen name="CitizenTabs" component={CitizenTabs} />
            <Stack.Screen name="ReportDetail" component={CitizenReportDetail}
              options={{ headerShown: true, title: 'Report Details', headerTintColor: '#1a237e' }} />
          </>
        )}
      </Stack.Navigator>
    </NavigationContainer>
  );
}

// ── Helpers ───────────────────────────────────────────────────────────────────

const COLORS = { active: '#1a237e', inactive: '#9e9e9e', bg: '#ffffff' };

const tabOptions = {
  tabBarActiveTintColor:   COLORS.active,
  tabBarInactiveTintColor: COLORS.inactive,
  tabBarStyle: { backgroundColor: COLORS.bg, borderTopWidth: 1, borderTopColor: '#e0e0e0' },
  headerShown: false,
};

function tabIcon(name) {
  return {
    tabBarIcon: ({ color, size, focused }) => (
      <Ionicons name={focused ? name : `${name}-outline`} size={size} color={color} />
    ),
  };
}
