import * as React from 'react';
import { useNavigate, Outlet } from 'react-router-dom';
import { styled, createTheme, ThemeProvider } from '@mui/material/styles';
import CssBaseline from '@mui/material/CssBaseline';

import MuiDrawer from '@mui/material/Drawer';
import MenuIcon from '@mui/icons-material/Menu';
import Person from '@mui/icons-material/Person';
import {
    Box, Toolbar, List, Typography, Divider, IconButton, Badge,
    Container, Link, ListItemButton, ListItemIcon, ListItemText
} from '@mui/material';

import MuiAppBar, { AppBarProps as MuiAppBarProps } from '@mui/material/AppBar';
import ChevronLeftIcon from '@mui/icons-material/ChevronLeft';
import NotificationsIcon from '@mui/icons-material/Notifications';
import DashboardIcon from '@mui/icons-material/Dashboard';
import ShoppingCartIcon from '@mui/icons-material/ShoppingCart';
import { Button } from '@mui/material';
import Cookies from 'js-cookie';
import Menu from '@mui/material/Menu';
import MenuItem from '@mui/material/MenuItem';
import { GoogleLogin } from '@react-oauth/google';
import { GoogleOAuthProvider, useGoogleLogin } from '@react-oauth/google';

interface GoogleTokenResponse {
    credential: string;
}


const googleClientId = "34471668497-aj0h4ifb4fe3dbcrijurdu04ahu1gurm.apps.googleusercontent.com"



const GoogleSignInButton = ({ setUserEmail }: { setUserEmail: React.Dispatch<React.SetStateAction<string>> }) => {
    const handleSuccess = async (response: any) => {
        console.log('Login Success:', response);
        // You can use the access token or profile data as per your need

        const token = response.access_token; // This is the ID token

        try {
            const apiResponse = await fetch('/demo/api/validate-google-token-bearer', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({ "token": token }),
            });

            if (apiResponse.ok) {
                const data = await apiResponse.json();
                console.log('User authenticated:', data);
                setUserEmail(Cookies.get('email') || "")
            } else {
                console.error('Failed to authenticate user');
            }
        } catch (error) {
            console.error('Error sending token to backend:', error);
        }
    };

    const handleError = () => {
        console.error('Login Failed');
    };

    // Use the useGoogleLogin hook to handle login functionality
    const login = useGoogleLogin({
        onSuccess: handleSuccess,
        onError: handleError,
    });

    return (
        <Box
            display="flex"
            justifyContent="center"
            alignItems="center"
            height="100vh"
        >
            <Button variant="contained" color="primary" onClick={() => login()}>
                Sign in with Google
            </Button>
        </Box>
    );
};


const GoogleLoginButton = ({ setUserEmail }: { setUserEmail: React.Dispatch<React.SetStateAction<string>> }) => {
    const handleSuccess = async (response: any) => {
        console.log('Login Success:', response);
        // You can use the access token or profile data as per your need

        const token = (response as GoogleTokenResponse).credential; // This is the ID token

        try {
            const apiResponse = await fetch('/demo/api/validate-google-token', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({ "token": token }),
            });

            if (apiResponse.ok) {
                const data = await apiResponse.json();
                console.log('User authenticated:', data);
                setUserEmail(Cookies.get('email') || "")
            } else {
                console.error('Failed to authenticate user');
            }
        } catch (error) {
            console.error('Error sending token to backend:', error);
        }
    };

    const handleError = () => {
        console.error('Login Failed');
    };

    return (
        <div>
            <GoogleLogin
                onSuccess={handleSuccess}
                onError={handleError}
            />
        </div>
    );
};

function Copyright(props: any) {
    return (
        <Typography variant="body2" color="text.secondary" align="center" {...props}>
            {'Copyright © '}
            <Link color="inherit" href="https://github.com/olitheolix/dfh">
                Oliver Nagy
            </Link>{' '}
            {new Date().getFullYear()}
            {'.'}
        </Typography>
    );
}

const drawerWidth: number = 240;

interface AppBarProps extends MuiAppBarProps {
    open?: boolean;
}

const AppBar = styled(MuiAppBar, {
    shouldForwardProp: (prop) => prop !== 'open',
})<AppBarProps>(({ theme, open }) => ({
    zIndex: theme.zIndex.drawer + 1,
    transition: theme.transitions.create(['width', 'margin'], {
        easing: theme.transitions.easing.sharp,
        duration: theme.transitions.duration.leavingScreen,
    }),
    ...(open && {
        marginLeft: drawerWidth,
        width: `calc(100% - ${drawerWidth}px)`,
        transition: theme.transitions.create(['width', 'margin'], {
            easing: theme.transitions.easing.sharp,
            duration: theme.transitions.duration.enteringScreen,
        }),
    }),
}));

const Drawer = styled(MuiDrawer, { shouldForwardProp: (prop) => prop !== 'open' })(
    ({ theme, open }) => ({
        '& .MuiDrawer-paper': {
            position: 'relative',
            whiteSpace: 'nowrap',
            width: drawerWidth,
            transition: theme.transitions.create('width', {
                easing: theme.transitions.easing.sharp,
                duration: theme.transitions.duration.enteringScreen,
            }),
            boxSizing: 'border-box',
            ...(!open && {
                overflowX: 'hidden',
                transition: theme.transitions.create('width', {
                    easing: theme.transitions.easing.sharp,
                    duration: theme.transitions.duration.leavingScreen,
                }),
                width: theme.spacing(7),
                [theme.breakpoints.up('sm')]: {
                    width: theme.spacing(9),
                },
            }),
        },
    }),
);

// TODO remove, this demo shouldn't need to reset the theme.
const defaultTheme = createTheme();

function ContextMenuLogout({ userEmail, setUserEmail }: { userEmail: string, setUserEmail: React.Dispatch<React.SetStateAction<string>> }) {
    const [contextMenu, setContextMenu] = React.useState<{
        mouseX: number;
        mouseY: number;
    } | null>(null);

    const handleContextMenu = (event: React.MouseEvent) => {
        event.preventDefault();
        setContextMenu(
            contextMenu === null
                ? {
                    mouseX: event.clientX + 2,
                    mouseY: event.clientY - 6,
                }
                : // repeated contextmenu when it is already open closes it with Chrome 84 on Ubuntu
                // Other native context menus might behave different.
                // With this behavior we prevent contextmenu from the backdrop to re-locale existing context menus.
                null,
        );
    };

    const handleClose = () => {
        setContextMenu(null);
        fetch('/demo/api/simulate-logout')
            .then(_ => { setUserEmail("") })
            .catch(error => {
                console.error('Error fetching data:');
            });
    };


    return (
        <div onContextMenu={handleContextMenu} style={{ cursor: 'context-menu' }}>
            <Typography>
                {userEmail}
            </Typography>
            <Menu
                open={contextMenu !== null}
                anchorReference="anchorPosition"
                anchorPosition={
                    contextMenu !== null
                        ? { top: contextMenu.mouseY, left: contextMenu.mouseX }
                        : undefined
                }
            >
                <MenuItem onClick={handleClose}>Logout</MenuItem>
            </Menu>
        </div>
    )
}


export default function Dashboard() {
    const [open, setOpen] = React.useState(true);
    const [userEmail, setUserEmail] = React.useState(Cookies.get('email') || "");
    const toggleDrawer = () => {
        setOpen(!open);
    };
    const navigate = useNavigate();
    const gotoCreateApp = () => {
        navigate('/new');
    };
    const gotoK8sOverviewDashboard = () => {
        navigate('/');
    };
    const gotoUserManagement = () => {
        navigate('/uam');
    };
    const gotoGroupManagement = () => {
        navigate('/uamgroups');
    };

    const onLogin = () => {
        fetch('/demo/api/simulate-login')
            .then(_ => {
                setUserEmail(Cookies.get('email') || "")
            })
            .catch(error => {
                console.error('Error fetching data:');
            });
    };

    const mainListItems = (
        <React.Fragment>
            <ListItemButton onClick={gotoK8sOverviewDashboard}>
                <ListItemIcon>
                    <DashboardIcon />
                </ListItemIcon>
                <ListItemText primary="Dashboard" />
            </ListItemButton>
            <ListItemButton onClick={gotoCreateApp}>
                <ListItemIcon>
                    <ShoppingCartIcon />
                </ListItemIcon>
                <ListItemText primary="New Application" />
            </ListItemButton>
            <ListItemButton onClick={gotoUserManagement}>
                <ListItemIcon>
                    <Person />
                </ListItemIcon>
                <ListItemText primary="Group Hierarchy" />
            </ListItemButton>
            <ListItemButton onClick={gotoGroupManagement}>
                <ListItemIcon>
                    <Person />
                </ListItemIcon>
                <ListItemText primary="Groups & Users" />
            </ListItemButton>
        </React.Fragment >
    );

    return (
        <ThemeProvider theme={defaultTheme}>
            <GoogleOAuthProvider clientId={googleClientId}>
                <Box sx={{ display: 'flex' }}>
                    <CssBaseline />
                    <AppBar position="absolute" open={open}>
                        <Toolbar
                            sx={{
                                pr: '24px', // keep right padding when drawer closed
                            }}
                        >
                            <IconButton
                                edge="start"
                                color="inherit"
                                aria-label="open drawer"
                                onClick={toggleDrawer}
                                sx={{
                                    marginRight: '36px',
                                    ...(open && { display: 'none' }),
                                }}
                            >
                                <MenuIcon />
                            </IconButton>
                            <Typography
                                component="h1"
                                variant="h6"
                                color="inherit"
                                noWrap
                                sx={{ flexGrow: 1 }}
                            >
                                Deployments For Humans
                            </Typography>
                            {userEmail != "" ? (<ContextMenuLogout userEmail={userEmail} setUserEmail={setUserEmail} />) : null}
                        </Toolbar>
                    </AppBar>
                    <Drawer variant="permanent" open={open}>
                        <Toolbar
                            sx={{
                                display: 'flex',
                                alignItems: 'center',
                                justifyContent: 'flex-end',
                                px: [1],
                            }}
                        >
                            <IconButton onClick={toggleDrawer}>
                                <ChevronLeftIcon />
                            </IconButton>
                        </Toolbar>
                        <Divider />
                        <List component="nav">
                            {mainListItems}
                            <Divider sx={{ my: 1 }} />
                        </List>
                    </Drawer>
                    <Box
                        component="main"
                        sx={{
                            backgroundColor: (theme) =>
                                theme.palette.mode === 'light'
                                    ? theme.palette.grey[100]
                                    : theme.palette.grey[900],
                            flexGrow: 1,
                            height: '100vh',
                            overflow: 'auto',
                        }}
                    >
                        <Toolbar />
                        <Container maxWidth={false} sx={{ mt: 6, mb: 6 }}>
                            {userEmail == "" ? <GoogleSignInButton setUserEmail={setUserEmail} /> : (<Outlet />)}
                            <Copyright sx={{ pt: 4 }} />
                        </Container>
                    </Box>
                </Box>
            </GoogleOAuthProvider>
        </ThemeProvider>
    );
}
