import * as React from "react";
import { useEffect, useContext } from "react";
import { useNavigate, Outlet } from "react-router-dom";
import CssBaseline from "@mui/material/CssBaseline";
import Cookies from "js-cookie";

import MuiDrawer from "@mui/material/Drawer";
import AccountTree from "@mui/icons-material/AccountTree";
import {
    alpha,
    styled,
    createTheme,
    ThemeProvider,
} from "@mui/material/styles";
import {
    Box,
    Button,
    Container,
    Dialog,
    DialogActions,
    DialogContent,
    DialogTitle,
    Divider,
    IconButton,
    Link,
    List,
    ListItemButton,
    ListItemIcon,
    ListItemText,
    Toolbar,
    Tooltip,
    Typography,
} from "@mui/material";

import { DFHToken } from "./UAMInterfaces";
import ContentCopyIcon from "@mui/icons-material/ContentCopy";

import MenuItem from "@mui/material/MenuItem";
import Menu, { MenuProps } from "@mui/material/Menu";
import { GoogleOAuthProvider, useGoogleLogin } from "@react-oauth/google";
import MuiAppBar, { AppBarProps as MuiAppBarProps } from "@mui/material/AppBar";

import MenuIcon from "@mui/icons-material/Menu";
import ApiIcon from "@mui/icons-material/Api";
import Person from "@mui/icons-material/Person";
import KeyboardArrowDownIcon from "@mui/icons-material/KeyboardArrowDown";
import ChevronLeftIcon from "@mui/icons-material/ChevronLeft";
import DashboardIcon from "@mui/icons-material/Dashboard";
import ShoppingCartIcon from "@mui/icons-material/ShoppingCart";
import {
    httpGet,
    httpPost,
    HTTPErrorContext,
    HTTPErrorContextType,
} from "./WebRequests";

const googleClientId = import.meta.env.VITE_GOOGLE_CLIENT_ID;

const StyledMenu = styled((props: MenuProps) => (
    <Menu
        elevation={0}
        anchorOrigin={{
            vertical: "bottom",
            horizontal: "right",
        }}
        transformOrigin={{
            vertical: "top",
            horizontal: "right",
        }}
        {...props}
    />
))(({ theme }) => ({
    "& .MuiPaper-root": {
        borderRadius: 6,
        marginTop: theme.spacing(1),
        minWidth: 180,
        color: "rgb(55, 65, 81)",
        boxShadow:
            "rgb(255, 255, 255) 0px 0px 0px 0px, rgba(0, 0, 0, 0.05) 0px 0px 0px 1px, rgba(0, 0, 0, 0.1) 0px 10px 15px -3px, rgba(0, 0, 0, 0.05) 0px 4px 6px -2px",
        "& .MuiMenu-list": {
            padding: "4px 0",
        },
        "& .MuiMenuItem-root": {
            "& .MuiSvgIcon-root": {
                fontSize: 18,
                color: theme.palette.text.secondary,
                marginRight: theme.spacing(1.5),
            },
            "&:active": {
                backgroundColor: alpha(
                    theme.palette.primary.main,
                    theme.palette.action.selectedOpacity,
                ),
            },
        },
        ...theme.applyStyles("dark", {
            color: theme.palette.grey[300],
        }),
    },
}));

function Copyright(props: any) {
    return (
        <Typography
            variant="body2"
            color="text.secondary"
            align="center"
            {...props}
        >
            {"Copyright © "}
            <Link color="inherit" href="https://github.com/olitheolix/dfh">
                Oliver Nagy
            </Link>{" "}
            {new Date().getFullYear()}
            {"."}
        </Typography>
    );
}

const drawerWidth: number = 240;

interface AppBarProps extends MuiAppBarProps {
    open?: boolean;
}

const AppBar = styled(MuiAppBar, {
    shouldForwardProp: (prop) => prop !== "open",
})<AppBarProps>(({ theme, open }) => ({
    zIndex: theme.zIndex.drawer + 1,
    transition: theme.transitions.create(["width", "margin"], {
        easing: theme.transitions.easing.sharp,
        duration: theme.transitions.duration.leavingScreen,
    }),
    ...(open && {
        marginLeft: drawerWidth,
        width: `calc(100% - ${drawerWidth}px)`,
        transition: theme.transitions.create(["width", "margin"], {
            easing: theme.transitions.easing.sharp,
            duration: theme.transitions.duration.enteringScreen,
        }),
    }),
}));

const Drawer = styled(MuiDrawer, {
    shouldForwardProp: (prop) => prop !== "open",
})(({ theme, open }) => ({
    "& .MuiDrawer-paper": {
        position: "relative",
        whiteSpace: "nowrap",
        width: drawerWidth,
        transition: theme.transitions.create("width", {
            easing: theme.transitions.easing.sharp,
            duration: theme.transitions.duration.enteringScreen,
        }),
        boxSizing: "border-box",
        ...(!open && {
            overflowX: "hidden",
            transition: theme.transitions.create("width", {
                easing: theme.transitions.easing.sharp,
                duration: theme.transitions.duration.leavingScreen,
            }),
            width: theme.spacing(7),
            [theme.breakpoints.up("sm")]: {
                width: theme.spacing(9),
            },
        }),
    },
}));

// TODO remove, this demo shouldn't need to reset the theme.
const defaultTheme = createTheme();

// Show a Google signin button to trigger the
const GoogleSignInButton = ({
    setUserEmail,
    errCtx,
}: {
    setUserEmail: React.Dispatch<React.SetStateAction<string>>;
    errCtx: HTTPErrorContextType;
}) => {
    const handleSuccess = async (response: any) => {
        console.log("Login Success:", response);
        // You can use the access token or profile data as per your need

        const token = response.access_token; // This is the ID token

        const ret = await httpPost(
            "/demo/api/auth/validate-google-bearer-token",
            {
                body: JSON.stringify({ token: token }),
            },
        );
        if (ret.err) {
            errCtx.showError(ret.err);
            return;
        }
        console.log("User authenticated:", ret.data);
        setUserEmail(Cookies.get("email") || "");
    };

    const handleError = () => {
        console.error("Login Failed");
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
            height="80vh"
        >
            <Button variant="contained" color="primary" onClick={() => login()}>
                Sign in with Google
            </Button>
        </Box>
    );
};

function ContextMenuLogout({
    userEmail,
    setUserEmail,
    errCtx,
}: {
    userEmail: string;
    setUserEmail: React.Dispatch<React.SetStateAction<string>>;
    errCtx: HTTPErrorContextType;
}) {
    const [anchorEl, setAnchorEl] = React.useState<null | HTMLElement>(null);
    const [openTokenDialog, setOpenTokenDialog] =
        React.useState<boolean>(false);
    const [tokenValue, setTokenValue] = React.useState<string>("");
    const open = Boolean(anchorEl);

    const handleClick = (event: React.MouseEvent<HTMLElement>) => {
        setAnchorEl(event.currentTarget);
    };
    const handleClose = () => {
        setAnchorEl(null);
    };

    const onLogout = async () => {
        handleClose();

        const ret = await httpGet("/demo/api/auth/clear-session");
        if (ret.err) {
            errCtx.showError(ret.err);
            return;
        }
        setUserEmail("");
    };

    const onLoadToken = async () => {
        const ret = await httpGet("/demo/api/auth/users/token");
        if (ret.err) {
            errCtx.showError(ret.err);
            return;
        }

        const data: DFHToken = ret.data;
        setOpenTokenDialog(true);
        setTokenValue(data.token);
        handleClose();
    };

    return (
        <div>
            <ShowAPITokenDialog
                isOpen={openTokenDialog}
                setIsOpen={setOpenTokenDialog}
                tokenValue={tokenValue}
            />
            <Button
                id="demo-customized-button"
                aria-controls={open ? "demo-customized-menu" : undefined}
                aria-haspopup="true"
                aria-expanded={open ? "true" : undefined}
                variant="contained"
                disableElevation
                onClick={handleClick}
                endIcon={<KeyboardArrowDownIcon />}
            >
                {userEmail}
            </Button>
            <StyledMenu
                id="demo-customized-menu"
                MenuListProps={{
                    "aria-labelledby": "demo-customized-button",
                }}
                anchorEl={anchorEl}
                open={open}
                onClose={handleClose}
            >
                <MenuItem onClick={onLoadToken} disableRipple>
                    <ApiIcon />
                    API Token
                </MenuItem>
                <MenuItem onClick={onLogout} disableRipple>
                    <Person />
                    Logout
                </MenuItem>
            </StyledMenu>
        </div>
    );
}

function ShowAPITokenDialog({
    isOpen,
    setIsOpen,
    tokenValue,
}: {
    isOpen: boolean;
    setIsOpen: React.Dispatch<React.SetStateAction<boolean>>;
    tokenValue: string;
}) {
    const [curlExample, setCurlExample] = React.useState(
        Cookies.get("email") || "",
    );

    const handleClose = () => {
        setIsOpen(false);
    };

    const handleCopyToken = () => {
        navigator.clipboard.writeText(tokenValue);
    };

    const handleCopyCurlExample = () => {
        navigator.clipboard.writeText(curlExample);
    };

    useEffect(() => {
        setCurlExample(
            `curl ${window.location.origin}/demo/api/auth/users/me -H "Authorization: Bearer ${tokenValue}"`,
        );
    }, [tokenValue]);

    return (
        <Dialog
            open={isOpen}
            onClose={handleClose}
            maxWidth="xl"
            fullWidth={true}
        >
            <DialogTitle>API Token</DialogTitle>
            <DialogContent>
                <Typography variant="body1" gutterBottom>
                    Bearer Token:
                </Typography>
                <Box
                    sx={{
                        maxWidth: "100%", // Ensures it fits within the dialog width
                        overflowX: "auto", // Enables horizontal scroll
                        backgroundColor: "#f5f5f5",
                        padding: 1,
                        borderRadius: 1,
                    }}
                >
                    <Typography component="pre" variant="body2">
                        <Tooltip title="Copy to Clipboard" arrow>
                            <IconButton onClick={handleCopyToken} size="small">
                                <ContentCopyIcon fontSize="small" />
                            </IconButton>
                        </Tooltip>
                        {tokenValue}
                    </Typography>
                </Box>
                <Typography variant="body1" gutterBottom>
                    Example usage:
                </Typography>
                <Box
                    sx={{
                        maxWidth: "100%", // Ensures it fits within the dialog width
                        overflowX: "auto", // Enables horizontal scroll
                        backgroundColor: "#f5f5f5",
                        padding: 1,
                        borderRadius: 1,
                    }}
                >
                    <Typography
                        component="pre"
                        variant="body2"
                        style={{ margin: 0, fontFamily: "monospace" }}
                    >
                        <Tooltip title="Copy to Clipboard" arrow>
                            <IconButton
                                onClick={handleCopyCurlExample}
                                size="small"
                            >
                                <ContentCopyIcon fontSize="small" />
                            </IconButton>
                        </Tooltip>
                        {curlExample}
                    </Typography>
                </Box>
            </DialogContent>
            <DialogActions>
                <Button
                    onClick={handleClose}
                    color="primary"
                    variant="contained"
                >
                    OK
                </Button>
            </DialogActions>
        </Dialog>
    );
}

export default function Dashboard() {
    const [open, setOpen] = React.useState(true);
    const [userEmail, setUserEmail] = React.useState(
        Cookies.get("email") || "",
    );
    const [errCtx, _] = React.useState<HTTPErrorContextType>(
        useContext(HTTPErrorContext),
    );

    const toggleDrawer = () => {
        setOpen(!open);
    };
    const navigate = useNavigate();
    const gotoCreateApp = () => {
        navigate("/new");
    };
    const gotoK8sOverviewDashboard = () => {
        navigate("/");
    };
    const gotoUserManagement = () => {
        navigate("/uam");
    };
    const gotoGroupManagement = () => {
        navigate("/uamgroups");
    };
    const gotoAPIDocs = () => {
        window.location.href = "/demo/api/docs";
    };

    const mainListItems = (
        <React.Fragment>
            <ListItemButton onClick={gotoK8sOverviewDashboard}>
                <ListItemIcon>
                    <DashboardIcon />
                </ListItemIcon>
                <ListItemText primary="App Overview" />
            </ListItemButton>
            <ListItemButton onClick={gotoCreateApp}>
                <ListItemIcon>
                    <ShoppingCartIcon />
                </ListItemIcon>
                <ListItemText primary="Deploy in <60s" />
            </ListItemButton>
            <ListItemButton onClick={gotoUserManagement}>
                <ListItemIcon>
                    <AccountTree />
                </ListItemIcon>
                <ListItemText primary="Group Hierarchy" />
            </ListItemButton>
            <ListItemButton onClick={gotoGroupManagement}>
                <ListItemIcon>
                    <Person />
                </ListItemIcon>
                <ListItemText primary="Groups & Users" />
            </ListItemButton>
            <Divider />
            <ListItemButton onClick={gotoAPIDocs}>
                <ListItemIcon>
                    <ApiIcon />
                </ListItemIcon>
                <ListItemText primary="API Docs" />
            </ListItemButton>
        </React.Fragment>
    );

    return (
        <ThemeProvider theme={defaultTheme}>
            <GoogleOAuthProvider clientId={googleClientId}>
                <Box sx={{ display: "flex" }}>
                    <CssBaseline />
                    <AppBar position="absolute" open={open}>
                        <Toolbar
                            sx={{
                                pr: "24px", // keep right padding when drawer closed
                            }}
                        >
                            <IconButton
                                edge="start"
                                color="inherit"
                                aria-label="open drawer"
                                onClick={toggleDrawer}
                                sx={{
                                    marginRight: "36px",
                                    ...(open && { display: "none" }),
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
                            {userEmail != "" ? (
                                <ContextMenuLogout
                                    userEmail={userEmail}
                                    setUserEmail={setUserEmail}
                                    errCtx={errCtx}
                                />
                            ) : null}
                        </Toolbar>
                    </AppBar>
                    <Drawer variant="permanent" open={open}>
                        <Toolbar
                            sx={{
                                display: "flex",
                                alignItems: "center",
                                justifyContent: "flex-end",
                                px: [1],
                            }}
                        >
                            <IconButton onClick={toggleDrawer}>
                                <ChevronLeftIcon />
                            </IconButton>
                        </Toolbar>
                        <Divider />
                        <List component="nav">{mainListItems}</List>
                    </Drawer>
                    <Box
                        component="main"
                        sx={{
                            backgroundColor: (theme) =>
                                theme.palette.mode === "light"
                                    ? theme.palette.grey[100]
                                    : theme.palette.grey[900],
                            flexGrow: 1,
                            height: "100vh",
                            overflow: "auto",
                        }}
                    >
                        <Toolbar />
                        <Container maxWidth={false} sx={{ mt: 6, mb: 6 }}>
                            {userEmail == "" ? (
                                <GoogleSignInButton
                                    setUserEmail={setUserEmail}
                                    errCtx={errCtx}
                                />
                            ) : (
                                <Outlet />
                            )}
                            <Copyright sx={{ pt: 4 }} />
                        </Container>
                    </Box>
                </Box>
            </GoogleOAuthProvider>
        </ThemeProvider>
    );
}
