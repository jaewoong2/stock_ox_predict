provider "oci" {}

resource "oci_core_instance" "generated_oci_core_instance" {
	agent_config {
		is_management_disabled = "false"
		is_monitoring_disabled = "false"
		plugins_config {
			desired_state = "DISABLED"
			name = "WebLogic Management Service"
		}
		plugins_config {
			desired_state = "DISABLED"
			name = "Vulnerability Scanning"
		}
		plugins_config {
			desired_state = "DISABLED"
			name = "Oracle Java Management Service"
		}
		plugins_config {
			desired_state = "DISABLED"
			name = "OS Management Hub Agent"
		}
		plugins_config {
			desired_state = "DISABLED"
			name = "Management Agent"
		}
		plugins_config {
			desired_state = "ENABLED"
			name = "Custom Logs Monitoring"
		}
		plugins_config {
			desired_state = "DISABLED"
			name = "Compute RDMA GPU Monitoring"
		}
		plugins_config {
			desired_state = "ENABLED"
			name = "Compute Instance Run Command"
		}
		plugins_config {
			desired_state = "ENABLED"
			name = "Compute Instance Monitoring"
		}
		plugins_config {
			desired_state = "DISABLED"
			name = "Compute HPC RDMA Auto-Configuration"
		}
		plugins_config {
			desired_state = "DISABLED"
			name = "Compute HPC RDMA Authentication"
		}
		plugins_config {
			desired_state = "ENABLED"
			name = "Cloud Guard Workload Protection"
		}
		plugins_config {
			desired_state = "DISABLED"
			name = "Block Volume Management"
		}
		plugins_config {
			desired_state = "DISABLED"
			name = "Bastion"
		}
	}
	availability_config {
		recovery_action = "RESTORE_INSTANCE"
	}
	availability_domain = "QeTQ:AP-CHUNCHEON-1-AD-1"
	compartment_id = "ocid1.tenancy.oc1..aaaaaaaad2zhczrlskhymyjos75qyfphrps4wfwti5rwav3u7mlsyogypila"
	create_vnic_details {
		assign_ipv6ip = "false"
		assign_private_dns_record = "false"
		assign_public_ip = "true"
		subnet_id = "ocid1.subnet.oc1.ap-chuncheon-1.aaaaaaaawjj4fgpm6n4sojftgbxckz2zmvue6r3wppmpmpiovjpwkqfqjrna"
	}
	display_name = "pg-a1"
	instance_options {
		are_legacy_imds_endpoints_disabled = "false"
	}
	is_pv_encryption_in_transit_enabled = "true"
	metadata = {
		"ssh_authorized_keys" = "ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABgQDO3smfjuTBbaFTphLhdnX7UibufSeabgdSC8Zki9ZVY1vKd3qxuaYgGgGFtMnt29xhl5x1gVvSd+o9UMonOOj7nKh8c5UrJiaMb+JkcnEtXHsWjeroZUT7rRSvjSE7genxMjQ1EfgasWdUrj2bGv5pc+hph+cGYzFfW0ghvBG0bw/grF6OJrOlS0PgBS1/n8nKEy3ZLYrEuf5LcRtu+dxkZ6HJ0bAXJvDVk9GlyF81Xzp0w0MU3tU0vbZp7Y2V8M+iO07FQoMRQJRw7WFPgBabkUTxFAyeu41O69ypAonFjtz9ykSo+AuGxdQuinFCFIa0v1gCaP9OitHVLumqzHaq2Be6VQq36YJhLWk0oMt9GXdlXo7zTD0vDVvX96FKsRWduZtuEzmPfaIRVm1rP05KOR9wyEt2ohyp2uW1GHBI5JzBbO6yM/NgGXxVT1TESPCq1ZNiBBWk/l9Su0KL3BfnmG4ug97O8ceEzzqhnfXV+ub+4e1HAHgFP1K+PWv4N7s= macbook@MacBookui-noteubug.local"
	}
	shape = "VM.Standard.A1.Flex"
	shape_config {
		memory_in_gbs = "6"
		ocpus = "1"
	}
	source_details {
		source_id = "ocid1.image.oc1.ap-chuncheon-1.aaaaaaaavkippkqc5i3s4xngceerbocusofxlznj7ovebts46uch6ra5nsga"
		source_type = "image"
	}
}
