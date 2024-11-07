import { useState, useEffect, useContext } from "react";
import Box from "@mui/material/Box";
import Grid from "@mui/material/Grid2";
import Title from "./Title";
import { SimpleTreeView } from "@mui/x-tree-view/SimpleTreeView";
import { TreeItem } from "@mui/x-tree-view/TreeItem";
import { DataGrid, GridColDef, GridToolbar } from "@mui/x-data-grid";
import {
    Autocomplete,
    Button,
    CircularProgress,
    Dialog,
    DialogActions,
    DialogContent,
    DialogTitle,
    Menu,
    MenuItem,
    Paper,
    TextField,
    Typography,
} from "@mui/material";
import { UAMUser, UAMGroup, DGUserRow, DGGroupRow, UAMChild } from "./UAMInterfaces";
import { GroupInfo } from "./UAMGroups";
import {
    httpGet,
    httpPut,
    httpDelete,
    HTTPErrorContext,
    HTTPErrorContextType,
} from "./WebRequests";

// Column headers of user table.
const DataGridUserColumns = [
    { field: "name", headerName: "Name", width: 200 },
    { field: "slack", headerName: "Slack", width: 100 },
    { field: "lanid", headerName: "LanID", width: 100 },
    { field: "email", headerName: "Email", width: 200 },
    { field: "role", headerName: "Role", width: 100 },
    { field: "manager", headerName: "Manager", flex: 1 },
];

/**
 * A dialog component for adding a group to an existing parent group within the UAM system.
 *
 * This dialog allows users to select an existing group and link it as a
 * child to a specified parent group.
 *
 * @component
 * isOpen - Boolean flag to control whether the dialog is open.
 * setIsOpen - Function to toggle the dialog's visibility.
 * info - Object containing information about the parent group.
 * setReloadGroups - Function to trigger a reload of group data post-update.
 * errCtx - Context to handle and display HTTP errors.
 *
 * @description
 * - Fetches a list of all available groups from the API upon opening to populate the dropdown.
 * - Provides options to cancel or confirm the group insertion.
 * - Error handling is performed via the provided `errCtx` context, displaying any backend errors.
 */
function LinkGroupDialog({
    isOpen,
    setIsOpen,
    info,
    setReloadGroups,
    errCtx,
}: {
    isOpen: boolean;
    setIsOpen: React.Dispatch<React.SetStateAction<boolean>>;
    info: ParentChildInfo;
    setReloadGroups: React.Dispatch<React.SetStateAction<boolean>>;
    errCtx: HTTPErrorContextType;
}) {
    const [options, setOptions] = useState<string[]>([]);
    const [groupName, setGroupName] = useState<string>("");

    // Load all available groups into an auto-complete/dropdown component.
    useEffect(() => {
        const fetchData = async () => {
            if (isOpen) {
                const ret = await httpGet("/demo/api/uam/v1/groups");
                if (ret.err) {
                    errCtx.showError(ret.err);
                    return;
                }
                const groupList = ret.data.map((user: UAMGroup) => {
                    return user.name;
                });
                setOptions(groupList);
            }
        };

        fetchData();
    }, [isOpen]);

    const closeDialog = () => {
        setIsOpen(false);
    };

    // Tell the API about the linked group once the user presses the Ok button.
    const onLink = async () => {
        if (groupName) {
            const payload: UAMChild = {
                child: groupName,
            };

            const ret = await httpPut(`/demo/api/uam/v1/groups/${info.child}/children`, {
                body: JSON.stringify(payload),
            });
            if (ret.err) {
                errCtx.showError(ret.err);
                return;
            }
            setReloadGroups(true);
        } else {
            console.warn("No group selected");
        }
        closeDialog();
    };

    return (
        <Dialog open={isOpen} onClose={closeDialog} fullWidth={true}>
            <DialogTitle>Add Group to {info.child}</DialogTitle>
            <DialogContent>
                <Grid container spacing={2} alignItems="center">
                    <Grid size={10}>
                        <Autocomplete
                            options={options}
                            value={groupName}
                            onChange={(_, newValue) => {
                                setGroupName(newValue || "");
                            }}
                            renderInput={(params) => (
                                <TextField
                                    {...params}
                                    label="group to add"
                                    variant="standard"
                                    fullWidth
                                />
                            )}
                        />
                    </Grid>
                </Grid>
            </DialogContent>
            <DialogActions>
                <Button onClick={closeDialog} color="primary">
                    Cancel
                </Button>
                <Button onClick={onLink} color="primary" variant="contained">
                    Insert
                </Button>
            </DialogActions>
        </Dialog>
    );
}

/**
 * A dialog component for unlinking a group from a parent.
 *
 * @component
 * isOpen - Boolean flag to control whether the dialog is open.
 * setIsOpen - Function to toggle the dialog's visibility.
 * info - Object containing information about the parent group.
 * setReloadGroups - Function to trigger a reload of group data post-update.
 * errCtx - Context to handle and display HTTP errors.
 *
 * @description
 * - Fetches a list of all available groups from the API upon opening to populate the dropdown.
 * - Provides options to cancel or confirm the group insertion.
 * - Error handling is performed via the provided `errCtx` context, displaying any backend errors.
 */
function UnlinkGroupDialog({
    isOpen,
    setIsOpen,
    info,
    setReloadGroups,
    errCtx,
}: {
    isOpen: boolean;
    setIsOpen: React.Dispatch<React.SetStateAction<boolean>>;
    info: ParentChildInfo;
    setReloadGroups: React.Dispatch<React.SetStateAction<boolean>>;
    errCtx: HTTPErrorContextType;
}) {
    const closeDialog = () => {
        setIsOpen(false);
    };

    // Instruct the API to unlink the group and close this dialog.
    const onUnlink = async () => {
        const ret = await httpDelete(
            `/demo/api/uam/v1/groups/${info.parent}/children/${info.child}`,
        );
        if (ret.err) {
            errCtx.showError(ret.err);
            return;
        }
        setReloadGroups(true);
        closeDialog();
    };

    return (
        <Dialog open={isOpen} onClose={closeDialog} fullWidth={true}>
            <DialogTitle>Unlink Group</DialogTitle>

            <DialogContent>
                <Typography>
                    Unlink
                    <Box component="span" fontWeight="bold" color="error.main" mx={0.3}>
                        {info.child}
                    </Box>
                    from
                    <Box component="span" fontWeight="bold" color="primary.main" mx={0.5}>
                        {info.parent}
                    </Box>
                    ?
                </Typography>
            </DialogContent>
            <DialogActions>
                <Button onClick={closeDialog} color="primary">
                    Cancel
                </Button>
                <Button onClick={onUnlink} color="error" variant="contained">
                    Unlink
                </Button>
            </DialogActions>
        </Dialog>
    );
}

interface ParentChildInfo {
    parent: string;
    child: string;
}

export default function UAMHierarchy() {
    const [loading, setLoading] = useState<boolean>(true);
    const [userGridRows, setUserGridRows] = useState<DGUserRow[]>([]);
    const [showAddGroupToGroupDialog, setShowAddGroupToGroupDialog] = useState<boolean>(false);
    const [showUnlinkGroupDialog, setShowUnlinkGroupDialog] = useState<boolean>(false);
    const [reloadGroups, setReloadGroups] = useState<boolean>(false);
    const [userGridColumns] = useState<GridColDef[]>(DataGridUserColumns);
    const [groupHierarchy, setGroupHierarchy] = useState<UAMGroup>({
        name: "n/a",
        owner: "n/a",
        provider: "",
        description: "",
        users: {},
        children: {},
        roles: [],
    });
    const [selectedGroup, setSelectedGroup] = useState<DGGroupRow>({
        id: "",
        name: "",
        owner: "",
        provider: "",
        description: "",
        children: {},
        users: {},
        roles: [],
    });
    const [linkInfo, setLinkInfo] = useState<ParentChildInfo>({
        parent: "",
        child: "",
    });
    const [errCtx, _] = useState<HTTPErrorContextType>(useContext(HTTPErrorContext));
    const [menuPosition, setMenuPosition] = useState<{
        top: number;
        left: number;
    } | null>(null);

    // Load the group hierarchy upon mounting the component or whenever the
    // TreeView needs a refresh.
    useEffect(() => {
        setReloadGroups(false);
        const fetchTree = async () => {
            const ret = await httpGet("/demo/api/uam/v1/tree");
            if (ret.err) {
                errCtx.showError(ret.err);
                return;
            }
            setGroupHierarchy(ret.data);
            setLoading(false);
        };
        fetchTree();
    }, [reloadGroups]);

    // User clicks on a group in the tree: load all its users into the data grid.
    const onGroupTreeClick = async (group: UAMGroup) => {
        const ret = await httpGet(`/demo/api/uam/v1/groups/${group.name}/users?recursive=1`);
        if (ret.err) {
            errCtx.showError(ret.err);
            return;
        }
        const users: DGUserRow[] = ret.data.map((user: UAMUser) => {
            return { id: user.email, ...user } as DGUserRow;
        });
        setUserGridRows(users);
        setSelectedGroup({ id: "", ...group });
    };

    // Render the group hierarchy into a TreeView. The backend API has a
    // bespoke endpoint for this task.
    const renderTree = (node: UAMGroup, keyPrefix: string = "", parentName: string = "") => {
        const cur = `${keyPrefix}/${node.name}`;
        return (
            <TreeItem
                key={cur}
                itemId={cur}
                label={node.name}
                onClick={() => onGroupTreeClick(node)}
                onContextMenu={(event: React.MouseEvent) =>
                    showAddRemoveMenu(event, parentName, node.name)
                }
            >
                {Object.entries(node.children)
                    .sort(([, a], [, b]) => a.name.localeCompare(b.name)) // Sort by `name` of each child node
                    .map(([_, child]) => renderTree(child, cur, node.name))}
            </TreeItem>
        );
    };

    if (loading) {
        return <CircularProgress />;
    }

    // Open Add/Delete context menu when user right-clicks on graph node.
    const showAddRemoveMenu = (event: React.MouseEvent, parent: string, child: string) => {
        event.preventDefault();
        event.stopPropagation();
        setLinkInfo({ parent: parent, child: child });
        setMenuPosition({
            top: event.clientY,
            left: event.clientX,
        });
    };

    // Close the Add/Delete context menu.
    const closeAddRemoveMenu = () => {
        setMenuPosition(null);
    };

    return (
        <Grid container spacing={2}>
            <Grid size={4} alignItems="left">
                <GroupInfo
                    selectedGroup={selectedGroup}
                    setSelectedGroup={setSelectedGroup}
                    setReloadGroups={setReloadGroups}
                    errCtx={errCtx}
                />

                {/* Group Hierarchy */}
                {loading ? (
                    <p>Loading...</p>
                ) : (
                    <Box sx={{ width: "100%", overflowX: "auto" }}>
                        <SimpleTreeView defaultSelectedItems={groupHierarchy.name}>
                            {renderTree(groupHierarchy, "", groupHierarchy.name)}
                        </SimpleTreeView>
                    </Box>
                )}
            </Grid>

            {/* Add/Remove group context menu when user right clicks on tree node.*/}
            <Menu
                open={!!menuPosition}
                onClose={closeAddRemoveMenu}
                anchorReference="anchorPosition"
                anchorPosition={
                    menuPosition ? { top: menuPosition.top, left: menuPosition.left } : undefined
                }
            >
                <MenuItem
                    onClick={() => {
                        closeAddRemoveMenu();
                        setShowAddGroupToGroupDialog(true);
                    }}
                >
                    Add
                </MenuItem>
                <MenuItem
                    onClick={() => {
                        closeAddRemoveMenu();
                        setShowUnlinkGroupDialog(true);
                    }}
                >
                    Unlink
                </MenuItem>
            </Menu>

            <LinkGroupDialog
                isOpen={showAddGroupToGroupDialog}
                setIsOpen={setShowAddGroupToGroupDialog}
                info={linkInfo}
                setReloadGroups={setReloadGroups}
                errCtx={errCtx}
            />
            <UnlinkGroupDialog
                isOpen={showUnlinkGroupDialog}
                setIsOpen={setShowUnlinkGroupDialog}
                info={linkInfo}
                setReloadGroups={setReloadGroups}
                errCtx={errCtx}
            />

            {/* Users in Selected Group */}
            <Grid size={8} justifyContent="center" alignItems="center">
                <Paper
                    style={{
                        padding: "20px",
                        display: "flex",
                        flexDirection: "column",
                    }}
                >
                    <Title>Users in {selectedGroup.name}</Title>
                    <Box height="70vh">
                        <DataGrid
                            disableColumnSelector
                            rows={userGridRows}
                            columns={userGridColumns}
                            slots={{ toolbar: GridToolbar }}
                            slotProps={{ toolbar: { showQuickFilter: true } }}
                            initialState={{
                                sorting: {
                                    sortModel: [{ field: "name", sort: "asc" }],
                                },
                            }}
                        />
                    </Box>
                </Paper>
            </Grid>
        </Grid>
    );
}
