import React from 'react';
import { useState, useEffect } from 'react';
import Box from '@mui/material/Box';
import { SimpleTreeView } from '@mui/x-tree-view/SimpleTreeView';
import { TreeItem } from '@mui/x-tree-view/TreeItem';
import Grid from '@mui/material/Grid2';
import { DataGrid } from '@mui/x-data-grid';
import { GridColDef } from '@mui/x-data-grid';
import { CircularProgress, Button } from '@mui/material';
import { GridToolbar } from '@mui/x-data-grid';
import { Paper, Typography } from '@mui/material';

import Title from './Title';
import { UAMUser, UAMGroup } from './UAMInterfaces'

const DataGridUserColumns = [
    { field: 'name', headerName: 'Name', width: 200 },
    { field: 'slack', headerName: 'Slack', width: 100 },
    { field: 'lanid', headerName: 'LanID', width: 100 },
    { field: 'email', headerName: 'Email', flex: 1 },
]

export default function UAMOverview() {
    const [treeData, setTreeData] = useState<UAMGroup>({
        uid: "n/a",
        name: "n/a",
        owner: "n/a",
        provider: "",
        users: [],
        children: [],
    });
    const [loading, setLoading] = useState<boolean>(true);
    const [error, setError] = useState<string | null>(null);
    const [dataGridRows, setDataGridRows] = useState<any[]>([]);
    const [columns, setColumns] = useState<GridColDef[]>(DataGridUserColumns);
    const [isUseraddModalOpen, setIsUseraddModalOpen] = useState<boolean>(false);
    const [selectedNode, setSelectedNode] = useState<string>("");

    useEffect(() => {
        fetch('/demo/api/tree')
            .then(response => response.json())
            .then(jsonData => {
                setTreeData(jsonData);
                setLoading(false);
            })
            .catch(error => { console.error('Error fetching data:', error); });
    }, []);

    const handleNodeSelect = (node: UAMGroup) => {
        fetch(`/demo/api/users/${node.uid}?recursive=1`)
            .then(response => response.json())
            .then(data => {
                const dataWithID = data.map((row: UAMUser) => {
                    return {
                        name: row.name,
                        email: row.email,
                        slack: row.slack,
                        lanid: row.lanid,
                        id: row.uid,
                    }
                })
                setDataGridRows(dataWithID);
                setSelectedNode(node.name)
            })
            .catch(error => {
                console.error('Error fetching data:', error);
            });
    };


    // Recursive function to render tree items
    const renderTree = (nodes: UAMGroup) => (
        < TreeItem key={nodes.uid} itemId={nodes.uid} label={nodes.name} onClick={() => handleNodeSelect(nodes)}>
            {nodes.children.map((node: UAMGroup) => renderTree(node))}
        </TreeItem >
    );

    if (loading) {
        return <CircularProgress />;
    }

    const onOpenUserAddDialog = async () => {
        setIsUseraddModalOpen(true)
    }

    return (
        <Grid container spacing={2}>
            <Grid size={4} alignItems="left">
                {/* Info Field */}
                <Paper style={{
                    padding: '20px', display: 'flex',
                    flexDirection: 'column',
                }} sx={{ mt: 0, mb: 6 }}>
                    <Title>Group</Title>

                    <Typography variant="subtitle1" gutterBottom>
                        Group: {selectedNode}
                    </Typography>
                </Paper>

                {/* TreeView section */}
                {loading ? (
                    <p>Loading...</p>
                ) : error ? (
                    <p>{error}</p>
                ) : (
                    <SimpleTreeView defaultSelectedItems={treeData.uid}>
                        {renderTree(treeData)}
                    </SimpleTreeView>
                )}

            </Grid>
            <Grid size={7} justifyContent="center" alignItems="center">
                <Paper style={{ padding: '20px', display: 'flex', flexDirection: 'column', }}>
                    <Title>Users in {selectedNode}</Title>
                    <Box height="70vh">
                        <DataGrid
                            disableColumnSelector
                            rows={dataGridRows}
                            columns={columns}
                            slots={{ toolbar: GridToolbar }}
                            slotProps={{
                                toolbar: {
                                    showQuickFilter: true,
                                },
                            }}
                        />
                    </Box >
                </Paper>

            </Grid>
        </Grid>
    );
};
